import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { DatePipe, DecimalPipe, TitleCasePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { ActivityListComponent } from '../shared/activity-list.component';
import { Activity } from '../models/activity.model';
import { FoodLog, DailyTotals, FALLBACK_GOAL, MACRO_FIELDS, MEAL_TYPES } from '../models/food.model';
import { DailyTargets } from '../models/profile.model';

const RING_RADIUS = 50;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
const CONFIRM_WINDOW_MS = 4000;

@Component({
  selector: 'app-food-log',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    TitleCasePipe,
    RouterLink,
    MatIconModule,
    MatSnackBarModule,
    ThemeToggleComponent,
    ActivityListComponent,
  ],
  templateUrl: './food-log.component.html',
  styleUrl: './food-log.component.scss',
})
export class FoodLogComponent implements OnInit, OnDestroy {
  private foodService = inject(FoodService);
  private snack = inject(MatSnackBar);

  logs: FoodLog[] = [];
  activities: Activity[] = [];
  totals: DailyTotals = {
    calories: 0, proteins: 0, carbs: 0, fats: 0, fiber: 0, saturated_fat: 0, salt: 0,
  };
  loading = true;
  /** Objetivos del perfil; mientras no haya datos se usa el de reserva. */
  targets: DailyTargets | null = null;
  readonly macroFields = MACRO_FIELDS.filter((m) => m.key !== 'salt' && m.key !== 'saturated_fat');
  mealTypes = MEAL_TYPES;
  today = new Date();

  /** Id del registro esperando confirmación de borrado (patrón de doble toque). */
  pendingDeleteId: number | null = null;
  private pendingTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.loadToday();
  }

  ngOnDestroy(): void {
    clearTimeout(this.pendingTimer);
  }

  trackLog(_index: number, log: FoodLog): number {
    return log.id;
  }

  loadToday(): void {
    this.loading = true;
    this.foodService.getToday().subscribe({
      next: (res) => {
        this.logs = res.items;
        this.activities = res.activities ?? [];
        this.totals = res.totals;
        this.targets = res.targets;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.snack.open('Error cargando el registro de hoy', 'OK');
      },
    });
  }

  get dailyGoal(): number {
    return this.targets?.calories ?? FALLBACK_GOAL;
  }

  get caloriePercent(): number {
    return Math.min((this.totals.calories / this.dailyGoal) * 100, 100);
  }

  get calorieOver(): boolean {
    return this.totals.calories > this.dailyGoal;
  }

  /** Objetivo de un macro concreto, si el perfil da para calcularlo. */
  targetOf(key: 'proteins' | 'carbs' | 'fats' | 'fiber'): number | null {
    return this.targets ? this.targets[key] : null;
  }

  macroPercent(key: 'proteins' | 'carbs' | 'fats' | 'fiber'): number {
    const goal = this.targetOf(key);
    if (!goal) return 0;
    return Math.min((this.totals[key] / goal) * 100, 100);
  }

  /** SVG ring: dashoffset 0 = lleno, circunferencia = vacío. */
  get ringOffset(): number {
    const filled = Math.min(this.totals.calories / this.dailyGoal, 1);
    return RING_CIRCUMFERENCE * (1 - filled);
  }

  get ringCircumference(): number {
    return RING_CIRCUMFERENCE;
  }

  getMealLabel(value: string): string {
    return this.mealTypes.find((m) => m.value === value)?.label ?? value;
  }

  getMealIcon(value: string): string {
    return this.mealTypes.find((m) => m.value === value)?.icon ?? 'restaurant';
  }

  onPhotoError(log: FoodLog): void {
    log.photo_url = null;
  }

  /** Primer toque arma la confirmación; el segundo borra. Se desarma solo. */
  requestDelete(log: FoodLog): void {
    if (this.pendingDeleteId === log.id) {
      this.confirmDelete(log);
      return;
    }
    clearTimeout(this.pendingTimer);
    this.pendingDeleteId = log.id;
    this.pendingTimer = setTimeout(() => (this.pendingDeleteId = null), CONFIRM_WINDOW_MS);
  }

  cancelDelete(): void {
    clearTimeout(this.pendingTimer);
    this.pendingDeleteId = null;
  }

  private confirmDelete(log: FoodLog): void {
    this.cancelDelete();
    this.foodService.deleteLog(log.id).subscribe({
      next: () => {
        this.snack.open('Registro eliminado', 'OK', { duration: 2500 });
        this.loadToday();
      },
      error: () => this.snack.open('Error al eliminar', 'OK'),
    });
  }
}
