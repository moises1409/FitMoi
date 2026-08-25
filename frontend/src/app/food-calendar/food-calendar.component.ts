import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe, NgTemplateOutlet, TitleCasePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { ActivityService } from '../services/activity.service';
import { WhoopService } from '../services/whoop.service';
import { DailyTargets } from '../models/profile.model';
import { Activity, ActivityFamily, DayActivityMark, FEELING_LABELS } from '../models/activity.model';
import { EnergyEntry } from '../models/energy.model';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { ActivityListComponent } from '../shared/activity-list.component';
import {
  FALLBACK_GOAL,
  MACRO_FIELDS,
  DaySummary,
  FoodLog,
  MEAL_TYPES,
  SummaryStats,
  Totals,
} from '../models/food.model';
import {
  addDays,
  addMonths,
  endOfMonth,
  fromISODate,
  isSameDay,
  monthGrid,
  startOfDay,
  startOfMonth,
  toISODate,
} from '../shared/date.utils';

/**
 * El calendario es siempre mensual; `day` no es una vista alternativa sino el
 * detalle al que se entra al tocar un día de la rejilla.
 */
export type CalendarMode = 'day' | 'month';

/** Una celda de la rejilla: la fecha más sus totales, si los hay. */
export interface DayCell {
  date: Date;
  iso: string;
  inRange: boolean;
  isToday: boolean;
  isSelected: boolean;
  calories: number;
  meals: number;
  /** Calorías gastadas ese día (0 si no se ha registrado). */
  burned: number;
  /** Familias con actividad ese día, para los puntos. */
  marks: DayActivityMark[];
  percent: number;
  over: boolean;
}

const EMPTY_TOTALS: Totals = {
  calories: 0, proteins: 0, carbs: 0, fats: 0, fiber: 0, saturated_fat: 0, salt: 0,
};
const CONFIRM_WINDOW_MS = 4000;

@Component({
  selector: 'app-food-calendar',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    TitleCasePipe,
    NgTemplateOutlet,
    RouterLink,
    MatIconModule,
    MatSnackBarModule,
    ThemeToggleComponent,
    ActivityListComponent,
  ],
  templateUrl: './food-calendar.component.html',
  styleUrl: './food-calendar.component.scss',
})
export class FoodCalendarComponent implements OnInit, OnDestroy {
  private foodService = inject(FoodService);
  private activityService = inject(ActivityService);
  private whoop = inject(WhoopService);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  /** Objetivo de calorias del perfil; de reserva mientras no haya datos. */
  goal = FALLBACK_GOAL;
  /** Objetivos del perfil, para pintar el progreso de cada macro. */
  targets = signal<DailyTargets | null>(null);
  readonly macroFields = MACRO_FIELDS.filter((m) => m.key !== 'salt' && m.key !== 'saturated_fat');
  readonly weekdayLabels = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

  mode = signal<CalendarMode>('month');
  anchor = signal<Date>(startOfDay(new Date()));
  loading = signal(true);

  /** Totales por día del rango visible, indexados por YYYY-MM-DD. */
  private summary = signal<Map<string, DaySummary>>(new Map());
  stats = signal<SummaryStats | null>(null);

  dayLogs = signal<FoodLog[]>([]);
  dayActivities = signal<Activity[]>([]);
  readonly families = this.activityService.families;
  private marksByDay = signal<Record<string, DayActivityMark[]>>({});
  /** Calorías gastadas por día del rango, para la rejilla del mes. */
  private energyByDay = signal<Record<string, number>>({});
  readonly feelingLabels = FEELING_LABELS;
  dayTotals = signal<Totals>(EMPTY_TOTALS);
  /** Gasto energético del día abierto (calorías gastadas); null si no hay. */
  dayEnergy = signal<EnergyEntry | null>(null);

  pendingDeleteId = signal<number | null>(null);
  private pendingTimer?: ReturnType<typeof setTimeout>;

  /** Whoop conectado en el servidor: solo entonces se muestra el botón de sync. */
  whoopConnected = signal(false);
  /** Sincronización de Whoop en curso, para desactivar el botón y girar el icono. */
  syncingWhoop = signal(false);

  // ── Derivados ──

  readonly isToday = computed(() => isSameDay(this.anchor(), new Date()));

  /** «Ir a hoy» solo aparece cuando no estás ya en el periodo actual. */
  readonly showTodayJump = computed(() => {
    const a = this.anchor();
    const now = new Date();
    if (this.mode() === 'month') {
      return a.getMonth() !== now.getMonth() || a.getFullYear() !== now.getFullYear();
    }
    return !isSameDay(a, now);
  });

  /** Fecha seleccionada en ISO, para pasarla a /add como día destino. */
  readonly anchorIso = computed(() => toISODate(this.anchor()));

  readonly weeks = computed<DayCell[][]>(() =>
    monthGrid(this.anchor()).map((week) => week.map((d) => this.toCell(d, this.anchor().getMonth()))),
  );

  readonly periodLabel = computed(() => {
    const a = this.anchor();
    if (this.mode() === 'month') {
      return a.toLocaleDateString('es', { month: 'long', year: 'numeric' });
    }
    return a.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
  });

  readonly dayPercent = computed(() =>
    Math.min((this.dayTotals().calories / this.goal) * 100, 100),
  );

  readonly dayOver = computed(() => this.dayTotals().calories > this.goal);

  /** Calorías gastadas del día abierto (0 si no se han registrado). */
  readonly dayBurned = computed(() => this.dayEnergy()?.calories ?? 0);

  /** Balance informativo consumido − gastado. Solo se muestra si hay gasto.
   *  Positivo = superávit (se comió más de lo que se gastó); negativo = déficit. */
  readonly dayBalance = computed(() => this.dayTotals().calories - this.dayBurned());
  readonly dayBalanceAbs = computed(() => Math.abs(this.dayBalance()));

  /** Objetivo de un macro, si el perfil da para calcularlo. */
  targetOf(key: 'proteins' | 'carbs' | 'fats' | 'fiber'): number | null {
    return this.targets() ? this.targets()![key] : null;
  }

  macroPercent(key: 'proteins' | 'carbs' | 'fats' | 'fiber'): number {
    const goal = this.targetOf(key);
    if (!goal) return 0;
    return Math.min((this.dayTotals()[key] / goal) * 100, 100);
  }

  // ── Ciclo de vida ──

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const mode = params.get('mode') as CalendarMode | null;
    const date = params.get('date');

    this.activityService.ensureFamilies().subscribe();
    // Silencioso: si Whoop no está configurado/conectado, el botón no aparece.
    this.whoop.status().subscribe({
      next: (s) => this.whoopConnected.set(s.connected),
      error: () => this.whoopConnected.set(false),
    });

    if (mode && ['day', 'month'].includes(mode)) this.mode.set(mode);
    if (date) {
      const parsed = fromISODate(date);
      if (!Number.isNaN(parsed.getTime())) this.anchor.set(parsed);
    }
    this.load();
  }

  ngOnDestroy(): void {
    clearTimeout(this.pendingTimer);
  }

  // ── Navegación ──

  /** Vuelve a la rejilla del mes desde el detalle de un día. */
  backToMonth(): void {
    if (this.mode() === 'month') return;
    this.mode.set('month');
    this.syncUrl();
    this.load();
  }

  shift(direction: -1 | 1): void {
    const a = this.anchor();
    if (this.mode() === 'month') this.anchor.set(addMonths(a, direction));
    else this.anchor.set(addDays(a, direction));
    this.syncUrl();
    this.load();
  }

  goToToday(): void {
    this.anchor.set(startOfDay(new Date()));
    this.syncUrl();
    this.load();
  }

  /** Al tocar un día se abre su detalle: es el gesto natural en un calendario. */
  openDay(cell: DayCell): void {
    this.anchor.set(cell.date);
    this.mode.set('day');
    this.syncUrl();
    this.load();
  }

  private syncUrl(): void {
    // Mantiene el estado en la URL para que atrás y recargar funcionen.
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { mode: this.mode(), date: toISODate(this.anchor()) },
      replaceUrl: true,
    });
  }

  // ── Carga ──

  load(): void {
    this.loading.set(true);
    this.mode() === 'day' ? this.loadDay() : this.loadRange();
  }

  private loadDay(): void {
    this.foodService.getDay(toISODate(this.anchor())).subscribe({
      next: (res) => {
        this.dayLogs.set(res.items);
        this.dayActivities.set(res.activities ?? []);
        this.dayEnergy.set(res.energy ?? null);
        this.dayTotals.set(res.totals);
        this.targets.set(res.targets);
        if (res.targets) this.goal = res.targets.calories;
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('Error cargando el día', 'OK');
      },
    });
  }

  private loadRange(): void {
    const a = this.anchor();
    const from = startOfMonth(a);
    const to = endOfMonth(a);

    this.foodService.getSummary(toISODate(from), toISODate(to)).subscribe({
      next: (res) => {
        this.summary.set(new Map(res.days.map((d) => [d.date, d])));
        this.marksByDay.set(res.activities_by_day ?? {});
        this.energyByDay.set(res.energy_by_day ?? {});
        this.stats.set(res.stats);
        this.targets.set(res.targets);
        if (res.targets) this.goal = res.targets.calories;
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('Error cargando el resumen', 'OK');
      },
    });
  }

  // ── Helpers de plantilla ──

  private toCell(date: Date, currentMonth: number): DayCell {
    const iso = toISODate(date);
    const entry = this.summary().get(iso);
    const calories = entry?.calories ?? 0;
    return {
      date,
      iso,
      inRange: currentMonth < 0 || date.getMonth() === currentMonth,
      isToday: isSameDay(date, new Date()),
      isSelected: isSameDay(date, this.anchor()),
      calories,
      meals: entry?.meals ?? 0,
      burned: this.energyByDay()[iso] ?? 0,
      marks: this.marksByDay()[iso] ?? [],
      percent: Math.min((calories / this.goal) * 100, 100),
      over: calories > this.goal,
    };
  }

  trackCell(_index: number, cell: DayCell): string {
    return cell.iso;
  }

  trackWeek(index: number): number {
    return index;
  }

  trackLog(_index: number, log: FoodLog): number {
    return log.id;
  }

  getMealLabel(value: string): string {
    return MEAL_TYPES.find((m) => m.value === value)?.label ?? value;
  }

  getMealIcon(value: string): string {
    return MEAL_TYPES.find((m) => m.value === value)?.icon ?? 'restaurant';
  }

  /** Color de una familia; el nombre siempre acompaña al color. */
  colorOf(family: string): string {
    return this.families().find((f) => f.key === family)?.color ?? '#4D7C0F';
  }

  labelOf(family: string): string {
    return this.families().find((f) => f.key === family)?.label ?? 'Otro';
  }

  iconOf(family: string): string {
    return this.families().find((f) => f.key === family)?.icon ?? 'sports';
  }

  /** Como mucho tres puntos por celda; el resto se resume con un "+". */
  visibleMarks(marks: DayActivityMark[]): DayActivityMark[] {
    return marks.slice(0, 3);
  }

  extraMarks(marks: DayActivityMark[]): number {
    return Math.max(marks.length - 3, 0);
  }

  trackActivity(_index: number, activity: Activity): number {
    return activity.id;
  }

  /** Sincroniza de Whoop los workouts y el gasto del día abierto, y recarga. */
  syncWhoop(): void {
    if (this.syncingWhoop()) return;
    this.syncingWhoop.set(true);
    this.whoop.sync(this.anchorIso()).subscribe({
      next: (res) => {
        this.syncingWhoop.set(false);
        const nuevas = res.created + res.updated;
        const energia = (res.energy?.created ?? 0) + (res.energy?.updated ?? 0);
        let msg: string;
        if (nuevas && energia) {
          msg = `Whoop: ${nuevas} actividad(es) y el gasto del día`;
        } else if (nuevas) {
          msg = `Whoop: ${res.created} nuevas, ${res.updated} actualizadas`;
        } else if (energia) {
          msg = 'Whoop: gasto del día actualizado';
        } else {
          msg = 'Whoop: sin novedades ese día';
        }
        this.snack.open(msg, 'OK', { duration: 3000 });
        if (nuevas || energia) this.loadDay();
      },
      error: () => {
        this.syncingWhoop.set(false);
        this.snack.open('No se pudo sincronizar con Whoop', 'OK');
      },
    });
  }

  onPhotoError(log: FoodLog): void {
    log.photo_url = null;
  }

  // ── Borrado desde el detalle del día ──

  requestDelete(log: FoodLog): void {
    if (this.pendingDeleteId() === log.id) {
      this.confirmDelete(log);
      return;
    }
    clearTimeout(this.pendingTimer);
    this.pendingDeleteId.set(log.id);
    this.pendingTimer = setTimeout(() => this.pendingDeleteId.set(null), CONFIRM_WINDOW_MS);
  }

  cancelDelete(): void {
    clearTimeout(this.pendingTimer);
    this.pendingDeleteId.set(null);
  }

  private confirmDelete(log: FoodLog): void {
    this.cancelDelete();
    this.foodService.deleteLog(log.id).subscribe({
      next: () => {
        this.snack.open('Registro eliminado', 'OK', { duration: 2500 });
        this.loadDay();
      },
      error: () => this.snack.open('Error al eliminar', 'OK'),
    });
  }
}
