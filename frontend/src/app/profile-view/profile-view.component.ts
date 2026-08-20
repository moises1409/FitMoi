import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ProfileService } from '../services/profile.service';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import {
  ACTIVITY_LABELS,
  GOAL_DIRECTIONS,
  JOB_ACTIVITY_LABELS,
  SEX_LABELS,
  UserProfile,
  WeightEntry,
} from '../models/profile.model';

type ListField = 'sports' | 'goals' | 'conditions' | 'injuries_current' | 'injuries_past' | 'diet_notes';

@Component({
  selector: 'app-profile-view',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    FormsModule,
    RouterLink,
    MatIconModule,
    MatSnackBarModule,
    ThemeToggleComponent,
  ],
  templateUrl: './profile-view.component.html',
  styleUrl: './profile-view.component.scss',
})
export class ProfileViewComponent implements OnInit {
  private profiles = inject(ProfileService);
  private snack = inject(MatSnackBar);

  readonly profile = this.profiles.profile;
  loading = signal(true);
  editing = signal(false);
  saving = signal(false);

  /** Copia de trabajo: nada se envía hasta pulsar Guardar. */
  draft = signal<Partial<UserProfile>>({});

  readonly sexOptions = Object.entries(SEX_LABELS).map(([value, label]) => ({ value, label }));
  readonly activityOptions = Object.entries(ACTIVITY_LABELS).map(([value, label]) => ({ value, label }));
  readonly jobOptions = Object.entries(JOB_ACTIVITY_LABELS).map(([value, label]) => ({ value, label }));
  readonly goalOptions = GOAL_DIRECTIONS;

  readonly listFields: { key: ListField; label: string; icon: string }[] = [
    { key: 'sports', label: 'Deportes', icon: 'directions_run' },
    { key: 'goals', label: 'Objetivos', icon: 'flag' },
    { key: 'conditions', label: 'Condiciones médicas', icon: 'medical_information' },
    { key: 'injuries_current', label: 'Lesiones actuales', icon: 'healing' },
    { key: 'injuries_past', label: 'Lesiones pasadas', icon: 'history' },
    { key: 'diet_notes', label: 'Alimentación', icon: 'restaurant_menu' },
  ];

  readonly isEmpty = computed(() => (this.profile()?.completeness ?? 0) === 0);

  // ── Peso ──
  newWeight: number | null = null;
  savingWeight = signal(false);
  showWeightForm = signal(false);
  pendingWeightDelete = signal<number | null>(null);

  readonly weight = computed(() => this.profile()?.weight ?? null);

  /** Con menos de 3 pesadas una gráfica no dice nada; se muestran los números. */
  readonly showChart = computed(() => (this.weight()?.entries.length ?? 0) >= 3);

  /**
   * Puntos de la línea en un viewBox de 100x32, con la fecha repartida en el
   * eje X y el peso normalizado entre el mínimo y el máximo del periodo.
   */
  readonly chartPoints = computed(() => {
    const entries = this.weight()?.entries ?? [];
    if (entries.length < 2) return '';

    const pesos = entries.map((e) => e.weight_kg);
    const min = Math.min(...pesos);
    const max = Math.max(...pesos);
    const rango = max - min || 1;

    return entries
      .map((e, i) => {
        const x = (i / (entries.length - 1)) * 100;
        const y = 30 - ((e.weight_kg - min) / rango) * 28;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  });

  /** La lista se lee de la pesada más reciente hacia atrás. */
  readonly reversedEntries = computed(() => (this.weight()?.entries ?? []).slice().reverse());

  /** Diferencia respecto a la pesada inmediatamente anterior. */
  deltaOfEntry(entry: WeightEntry): number | null {
    const entries = this.weight()?.entries ?? [];
    const i = entries.findIndex((e) => e.id === entry.id);
    if (i <= 0) return null;
    return Math.round((entries[i].weight_kg - entries[i - 1].weight_kg) * 10) / 10;
  }

  openWeightForm(): void {
    this.newWeight = this.weight()?.current ?? null;
    this.showWeightForm.set(true);
  }

  saveWeight(): void {
    const value = Number(this.newWeight);
    if (!Number.isFinite(value) || value <= 0 || this.savingWeight()) return;
    this.savingWeight.set(true);

    this.profiles.addWeight(value).subscribe({
      next: () => {
        this.savingWeight.set(false);
        this.showWeightForm.set(false);
        this.snack.open('Pesada registrada', 'OK', { duration: 2500 });
      },
      error: (err) => {
        this.savingWeight.set(false);
        this.snack.open(err?.error?.error ?? 'No se pudo guardar', 'OK', { duration: 5000 });
      },
    });
  }

  requestWeightDelete(entry: WeightEntry): void {
    if (this.pendingWeightDelete() === entry.id) {
      this.profiles.deleteWeight(entry.id).subscribe({
        next: () => {
          this.pendingWeightDelete.set(null);
          this.snack.open('Pesada eliminada', 'OK', { duration: 2500 });
        },
        error: () => this.snack.open('No se pudo eliminar', 'OK'),
      });
      return;
    }
    this.pendingWeightDelete.set(entry.id);
    setTimeout(() => {
      if (this.pendingWeightDelete() === entry.id) this.pendingWeightDelete.set(null);
    }, 4000);
  }

  ngOnInit(): void {
    this.profiles.load().subscribe({
      next: () => this.loading.set(false),
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar tu perfil', 'OK');
      },
    });
  }

  sexLabel(value: string | null): string {
    return value ? (SEX_LABELS[value] ?? value) : '—';
  }

  activityLabel(value: string | null): string {
    return value ? (ACTIVITY_LABELS[value] ?? value) : '—';
  }

  jobLabel(value: string | null): string {
    return value ? (JOB_ACTIVITY_LABELS[value] ?? value) : '—';
  }

  // ── Edición ──
  startEdit(): void {
    const p = this.profile();
    if (!p) return;
    this.draft.set({
      age: p.age, sex: p.sex, weight_kg: p.weight_kg, height_cm: p.height_cm,
      training_days_per_week: p.training_days_per_week,
      activity_level: p.activity_level, job_activity: p.job_activity,
      job: p.job, location: p.location, primary_goal: p.primary_goal,
      free_notes: p.free_notes,
      goal_direction: p.goal_direction ?? p.targets?.goal_direction ?? null,
      weight_check_every_days: p.weight_check_every_days ?? 30,
      target_overrides: { ...p.target_overrides },
      sports: [...p.sports], goals: [...p.goals], conditions: [...p.conditions],
      injuries_current: [...p.injuries_current], injuries_past: [...p.injuries_past],
      diet_notes: [...p.diet_notes],
    });
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
    this.draft.set({});
  }

  patch(key: string, value: unknown): void {
    this.draft.update((d) => ({ ...d, [key]: value }));
  }

  listOf(key: ListField): string[] {
    return (this.draft()[key] as string[]) ?? [];
  }

  patchListItem(key: ListField, index: number, value: string): void {
    this.patch(key, this.listOf(key).map((v, i) => (i === index ? value : v)));
  }

  addListItem(key: ListField): void {
    this.patch(key, [...this.listOf(key), '']);
  }

  removeListItem(key: ListField, index: number): void {
    this.patch(key, this.listOf(key).filter((_, i) => i !== index));
  }

  /** Objetivo fijado a mano, o vacío si se usa el calculado. */
  overrideOf(key: string): number | null {
    return (this.draft().target_overrides ?? {})[key] ?? null;
  }

  patchOverride(key: string, value: unknown): void {
    const overrides = { ...(this.draft().target_overrides ?? {}) };
    const n = Number(value);
    if (value === '' || value === null || !Number.isFinite(n) || n <= 0) delete overrides[key];
    else overrides[key] = Math.round(n);
    this.patch('target_overrides', overrides);
  }

  save(): void {
    if (this.saving()) return;
    this.saving.set(true);

    // Las listas se limpian de entradas vacías antes de enviarlas.
    const payload: Record<string, unknown> = { ...this.draft() };
    for (const { key } of this.listFields) {
      const list = (payload[key] as string[] | undefined) ?? [];
      payload[key] = list.map((v) => v.trim()).filter(Boolean);
    }

    this.profiles.update(payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.editing.set(false);
        this.snack.open('Perfil actualizado', 'OK', { duration: 2500 });
      },
      error: (err) => {
        this.saving.set(false);
        this.snack.open(err?.error?.error ?? 'No se pudo guardar', 'OK', { duration: 5000 });
      },
    });
  }
}
