import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe, NgTemplateOutlet, TitleCasePipe } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { ActivityService } from '../services/activity.service';
import { DailyTargets } from '../models/profile.model';
import { Activity, ActivityFamily, DayActivityMark, FEELING_LABELS } from '../models/activity.model';
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
  startOfWeek,
  toISODate,
  weekDays,
} from '../shared/date.utils';

export type CalendarMode = 'day' | 'week' | 'month';

/** Una celda de la rejilla: la fecha más sus totales, si los hay. */
export interface DayCell {
  date: Date;
  iso: string;
  inRange: boolean;
  isToday: boolean;
  isSelected: boolean;
  calories: number;
  meals: number;
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
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  /** Objetivo de calorias del perfil; de reserva mientras no haya datos. */
  goal = FALLBACK_GOAL;
  /** Objetivos del perfil, para pintar el progreso de cada macro. */
  targets = signal<DailyTargets | null>(null);
  readonly macroFields = MACRO_FIELDS.filter((m) => m.key !== 'salt' && m.key !== 'saturated_fat');
  readonly weekdayLabels = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  readonly modes: { value: CalendarMode; label: string; icon: string }[] = [
    { value: 'day', label: 'Día', icon: 'today' },
    { value: 'week', label: 'Semana', icon: 'date_range' },
    { value: 'month', label: 'Mes', icon: 'calendar_month' },
  ];

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
  readonly feelingLabels = FEELING_LABELS;
  dayTotals = signal<Totals>(EMPTY_TOTALS);

  pendingDeleteId = signal<number | null>(null);
  private pendingTimer?: ReturnType<typeof setTimeout>;

  // ── Derivados ──

  readonly isToday = computed(() => isSameDay(this.anchor(), new Date()));

  /** Fecha seleccionada en ISO, para pasarla a /add como día destino. */
  readonly anchorIso = computed(() => toISODate(this.anchor()));

  readonly weeks = computed<DayCell[][]>(() =>
    monthGrid(this.anchor()).map((week) => week.map((d) => this.toCell(d, this.anchor().getMonth()))),
  );

  readonly week = computed<DayCell[]>(() =>
    weekDays(this.anchor()).map((d) => this.toCell(d, -1)),
  );

  /** Escala de las barras de la semana: el mayor entre el objetivo y el pico. */
  readonly weekPeak = computed(() =>
    Math.max(this.goal, ...this.week().map((d) => d.calories)),
  );

  readonly periodLabel = computed(() => {
    const a = this.anchor();
    if (this.mode() === 'month') {
      return a.toLocaleDateString('es', { month: 'long', year: 'numeric' });
    }
    if (this.mode() === 'week') {
      const days = weekDays(a);
      const from = days[0];
      const to = days[6];
      const sameMonth = from.getMonth() === to.getMonth();
      const fromLabel = from.toLocaleDateString('es', {
        day: 'numeric',
        month: sameMonth ? undefined : 'short',
      });
      const toLabel = to.toLocaleDateString('es', { day: 'numeric', month: 'short' });
      return `${fromLabel} – ${toLabel}`;
    }
    return a.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
  });

  readonly dayPercent = computed(() =>
    Math.min((this.dayTotals().calories / this.goal) * 100, 100),
  );

  readonly dayOver = computed(() => this.dayTotals().calories > this.goal);

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

    if (mode && ['day', 'week', 'month'].includes(mode)) this.mode.set(mode);
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

  setMode(mode: CalendarMode): void {
    if (this.mode() === mode) return;
    this.mode.set(mode);
    this.syncUrl();
    this.load();
  }

  shift(direction: -1 | 1): void {
    const a = this.anchor();
    if (this.mode() === 'month') this.anchor.set(addMonths(a, direction));
    else if (this.mode() === 'week') this.anchor.set(addDays(a, 7 * direction));
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
    const [from, to] =
      this.mode() === 'month'
        ? [startOfMonth(a), endOfMonth(a)]
        : [startOfWeek(a), addDays(startOfWeek(a), 6)];

    this.foodService.getSummary(toISODate(from), toISODate(to)).subscribe({
      next: (res) => {
        this.summary.set(new Map(res.days.map((d) => [d.date, d])));
        this.marksByDay.set(res.activities_by_day ?? {});
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

  onPhotoError(log: FoodLog): void {
    log.photo_url = null;
  }

  barHeight(cell: DayCell): number {
    return cell.calories ? Math.max((cell.calories / this.weekPeak()) * 100, 4) : 0;
  }

  goalLinePosition(): number {
    return (this.goal / this.weekPeak()) * 100;
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
