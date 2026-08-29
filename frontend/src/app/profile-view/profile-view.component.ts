import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { AuthService } from '../services/auth.service';
import { ProfileService } from '../services/profile.service';
import { WithingsService } from '../services/withings.service';
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
  private withings = inject(WithingsService);
  private snack = inject(MatSnackBar);
  private auth = inject(AuthService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly profile = this.profiles.profile;
  /** Solo se ofrece cerrar sesión si el candado está activo. */
  readonly authRequired = this.auth.required;
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

  // ── Withings (báscula) ──
  /** Configurada en el servidor: solo entonces se ofrece conectar. */
  withingsConfigured = signal(false);
  /** Conectada: se ofrece sincronizar y se muestra la composición. */
  withingsConnected = signal(false);
  syncingWithings = signal(false);

  /**
   * Evolución de la composición corporal (báscula Withings). Para cada métrica
   * recorre el histórico de pesadas y devuelve el valor actual, el cambio desde
   * la primera medición y los puntos de una mini-gráfica, para poder medir el
   * progreso en el tiempo. Solo aparece cada métrica si hay al menos un dato.
   */
  readonly compositionTrends = computed(() => {
    const entries = this.weight()?.entries ?? []; // cronológico: antigua → reciente
    const metrics: { key: keyof WeightEntry; label: string; color: string }[] = [
      { key: 'fat_ratio', label: 'Masa grasa', color: '#0891B2' },
      { key: 'muscle_ratio', label: 'Masa muscular', color: '#6C4DE0' },
      { key: 'bone_ratio', label: 'Masa ósea', color: '#4D7C0F' },
      { key: 'water_ratio', label: 'Agua corporal', color: '#0EA5E9' },
    ];

    return metrics
      .map((m) => {
        const serie = entries
          .map((e) => e[m.key] as number | null)
          .filter((v): v is number => v !== null);
        if (!serie.length) return null;
        const current = serie[serie.length - 1];
        const delta = serie.length > 1 ? Math.round((current - serie[0]) * 10) / 10 : null;
        return {
          ...m,
          current,
          delta,
          // La mini-gráfica solo dice algo con 3+ puntos; con menos, solo números.
          points: serie.length >= 3 ? this.sparkline(serie) : '',
        };
      })
      .filter((m): m is NonNullable<typeof m> => m !== null);
  });

  /** ¿La última pesada trae composición? (para decidir si se pinta la sección). */
  readonly hasComposition = computed(() => this.compositionTrends().length > 0);

  /**
   * Normaliza una serie de valores a puntos de un viewBox 100x24 para una
   * mini-gráfica (misma idea que la del peso, reutilizable por métrica).
   */
  sparkline(values: number[]): string {
    if (values.length < 2) return '';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const rango = max - min || 1;
    return values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * 100;
        const y = 22 - ((v - min) / rango) * 20;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
  }

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

    // Estado de la báscula: silencioso. Si no está configurada, no aparece nada.
    this.withings.status().subscribe({
      next: (s) => {
        this.withingsConfigured.set(s.configured);
        this.withingsConnected.set(s.connected);
      },
      error: () => {
        this.withingsConfigured.set(false);
        this.withingsConnected.set(false);
      },
    });

    this.handleWithingsReturn();
  }

  /** Al volver del OAuth de Withings (?withings=connected|error) se avisa y se
   * limpia la query para que un refresco no repita el mensaje. */
  private handleWithingsReturn(): void {
    const params = this.route.snapshot.queryParamMap;
    const outcome = params.get('withings');
    if (!outcome) return;

    if (outcome === 'connected') {
      this.withingsConnected.set(true);
      this.snack.open('Báscula Withings conectada', 'OK', { duration: 3000 });
    } else if (outcome === 'error') {
      const reason = params.get('reason') || 'No se pudo conectar la báscula';
      this.snack.open(reason, 'OK', { duration: 6000 });
    }
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
  }

  /** Lanza el flujo OAuth para conectar la báscula (navega fuera de la app). */
  connectWithings(): void {
    this.withings.connect();
  }

  /** Trae de Withings las pesadas recientes y recarga el perfil. */
  syncWithings(): void {
    if (this.syncingWithings()) return;
    this.syncingWithings.set(true);
    this.withings.sync().subscribe({
      next: (res) => {
        const nuevas = res.created + res.updated;
        this.profiles.load().subscribe();
        this.syncingWithings.set(false);
        this.snack.open(
          nuevas ? `Withings: ${nuevas} pesada(s) sincronizada(s)` : 'Withings: sin novedades',
          'OK',
          { duration: 3000 },
        );
      },
      error: (err) => {
        this.syncingWithings.set(false);
        this.snack.open(err?.error?.error ?? 'No se pudo sincronizar con Withings', 'OK', { duration: 5000 });
      },
    });
  }

  /** Desconecta la báscula (olvida el token en el servidor). */
  disconnectWithings(): void {
    this.withings.disconnect().subscribe({
      next: () => {
        this.withingsConnected.set(false);
        this.snack.open('Báscula Withings desconectada', 'OK', { duration: 3000 });
      },
      error: () => this.snack.open('No se pudo desconectar', 'OK'),
    });
  }

  logout(): void {
    this.auth.logout().subscribe({
      next: () => this.router.navigate(['/login']),
      error: () => this.router.navigate(['/login']),
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
