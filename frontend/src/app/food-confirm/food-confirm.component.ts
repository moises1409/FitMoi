import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { EntryDraftService } from '../services/entry-draft.service';
import { FoodItem, MACRO_FIELDS, MEAL_TYPES, MacroKey, PORTION_PRESETS } from '../models/food.model';
import { isSameDay, toISODate } from '../shared/date.utils';

@Component({
  selector: 'app-food-confirm',
  standalone: true,
  imports: [DecimalPipe, FormsModule, MatIconModule, MatSnackBarModule],
  templateUrl: './food-confirm.component.html',
  styleUrl: './food-confirm.component.scss',
})
export class FoodConfirmComponent implements OnInit {
  private foodService = inject(FoodService);
  private router = inject(Router);
  private snack = inject(MatSnackBar);
  readonly drafts = inject(EntryDraftService);

  readonly mealTypes = MEAL_TYPES;
  readonly portions = PORTION_PRESETS;
  readonly macroFields = MACRO_FIELDS;

  saving = signal(false);
  editing = signal(false);
  showDetail = signal(true);

  /** Estimación de porciones y valoración que devolvió el análisis. */
  readonly detail = computed(() => this.drafts.draft()?.analysis ?? null);

  readonly hasAssessment = computed(() => {
    const a = this.detail()?.assessment;
    return !!(a && (a.summary || a.positives?.length || a.concerns?.length || a.tip));
  });

  /** Rango de calorías escalado a la porción elegida. */
  readonly calorieRange = computed(() => {
    const d = this.drafts.draft();
    const detail = this.detail();
    if (!d || !detail?.calories_min || !detail?.calories_max) return null;
    return {
      min: Math.round(detail.calories_min * d.portion),
      max: Math.round(detail.calories_max * d.portion),
    };
  });

  /** Gramos del alimento escalados: si comes 1,5× también pesa 1,5×. */
  foodGrams(food: FoodItem): number | null {
    const portion = this.drafts.draft()?.portion ?? 1;
    return food.grams ? Math.round(food.grams * portion) : null;
  }

  foodCalories(food: FoodItem): number {
    const portion = this.drafts.draft()?.portion ?? 1;
    return Math.round((food.calories || 0) * portion);
  }

  trackFood(_index: number, food: FoodItem): string {
    return food.name;
  }

  /** logged_at se guarda como 'YYYY-MM-DDTHH:mm'; los inputs nativos lo parten. */
  readonly date = computed(() => this.drafts.draft()?.logged_at.slice(0, 10) ?? '');
  readonly time = computed(() => this.drafts.draft()?.logged_at.slice(11, 16) ?? '');

  readonly whenLabel = computed(() => {
    const iso = this.drafts.draft()?.logged_at;
    if (!iso) return '';
    const d = new Date(iso);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);

    if (isSameDay(d, today)) return 'Hoy';
    if (isSameDay(d, yesterday)) return 'Ayer';
    return d.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
  });

  ngOnInit(): void {
    // Sin borrador no hay nada que confirmar (p. ej. al entrar por la URL).
    if (!this.drafts.draft()) this.router.navigate(['/add']);
  }

  scaled(key: MacroKey): number {
    return this.drafts.scaled(key);
  }

  setPortion(portion: number): void {
    const value = Math.min(Math.max(Number(portion) || 0, 0.05), 20);
    this.drafts.patch({ portion: Math.round(value * 100) / 100 });
  }

  onMacroChange(key: MacroKey, value: unknown): void {
    const draft = this.drafts.draft();
    if (!draft) return;
    const n = Number(value);
    const safe = Number.isFinite(n) && n > 0 ? Math.round(n * 10) / 10 : 0;
    // Se edita el valor visible (escalado); se guarda el de 1 porción.
    this.drafts.patch({ [key]: draft.portion ? safe / draft.portion : safe });
  }

  setDate(value: string): void {
    if (value) this.drafts.patch({ logged_at: `${value}T${this.time() || '12:00'}` });
  }

  setTime(value: string): void {
    if (value) this.drafts.patch({ logged_at: `${this.date()}T${value}` });
  }

  shiftDay(days: number): void {
    const d = new Date(this.drafts.draft()?.logged_at ?? Date.now());
    d.setDate(d.getDate() + days);
    this.setDate(toISODate(d));
  }

  setNow(): void {
    const now = new Date();
    const p = (n: number) => `${n}`.padStart(2, '0');
    this.drafts.patch({
      logged_at: `${toISODate(now)}T${p(now.getHours())}:${p(now.getMinutes())}`,
    });
  }

  save(): void {
    const payload = this.drafts.toPayload();
    if (!payload || this.saving()) return;
    this.saving.set(true);

    const targetDate = this.date();

    this.foodService.saveLog(payload).subscribe({
      next: () => {
        this.drafts.clear();
        this.snack.open('Comida guardada', 'OK', { duration: 2200 });
        // Vuelve al detalle del día al que se ha añadido, dentro del calendario.
        this.router.navigate(['/calendar'], {
          queryParams: { mode: 'day', date: targetDate },
        });
      },
      error: (err) => {
        this.saving.set(false);
        this.snack.open(
          err?.error?.error ?? 'Error al guardar. Inténtalo de nuevo.',
          'OK',
          { duration: 6000 },
        );
      },
    });
  }

  cancel(): void {
    const date = this.date();
    this.drafts.clear();
    this.router.navigate(['/add'], { queryParams: date ? { date } : {} });
  }
}
