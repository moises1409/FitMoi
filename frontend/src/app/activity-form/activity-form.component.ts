import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivityService } from '../services/activity.service';
import {
  ActivityFamily,
  FEELING_LABELS,
  SPORT_SUGGESTIONS,
} from '../models/activity.model';
import { toISODate } from '../shared/date.utils';

@Component({
  selector: 'app-activity-form',
  standalone: true,
  imports: [FormsModule, MatIconModule, MatSnackBarModule],
  templateUrl: './activity-form.component.html',
  styleUrl: './activity-form.component.scss',
})
export class ActivityFormComponent implements OnInit {
  private activities = inject(ActivityService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private snack = inject(MatSnackBar);

  readonly suggestions = SPORT_SUGGESTIONS;
  readonly feelings = [1, 2, 3, 4, 5];
  readonly feelingLabels = FEELING_LABELS;
  readonly families = this.activities.families;

  sportName = '';
  durationMin: number | null = null;
  calories: number | null = null;
  feeling: number | null = null;
  notes = '';
  date = '';
  time = '';

  /** Familia elegida a mano; si se deja vacía se deduce del nombre. */
  manualFamily = signal<string | null>(null);
  saving = signal(false);
  /** Id cuando se está editando una actividad existente. */
  editingId = signal<number | null>(null);
  loading = signal(false);

  /** Día al que se añade, arrastrado desde el calendario. */
  private targetDate: string | null = null;

  /** La familia que se guardará: la elegida, o la que sugiere el nombre. */
  readonly family = computed<ActivityFamily | undefined>(() => {
    const manual = this.manualFamily();
    if (manual) return this.activities.familyOf(manual);
    return this.activities.familyOf(this.guessFamily(this.sportNameValue()));
  });

  /** Señal auxiliar: el nombre se teclea con ngModel, no es señal por sí solo. */
  private sportSignal = signal('');
  private sportNameValue = () => this.sportSignal();

  ngOnInit(): void {
    this.activities.ensureFamilies().subscribe();

    const id = this.route.snapshot.queryParamMap.get('id');
    if (id) {
      this.loadForEdit(Number(id));
      return;
    }

    this.targetDate = this.route.snapshot.queryParamMap.get('date');
    const now = new Date();
    this.date = this.targetDate ?? toISODate(now);
    // En un día pasado, una hora razonable en vez de la actual.
    this.time = this.targetDate && this.targetDate !== toISODate(now)
      ? '18:00'
      : `${`${now.getHours()}`.padStart(2, '0')}:${`${now.getMinutes()}`.padStart(2, '0')}`;
  }

  private loadForEdit(id: number): void {
    this.loading.set(true);
    this.activities.get(id).subscribe({
      next: (a) => {
        this.editingId.set(a.id);
        this.onSportChange(a.sport_name);
        this.manualFamily.set(a.activity_type);
        this.durationMin = a.duration_min;
        this.calories = a.calories;
        this.feeling = a.feeling;
        this.notes = a.notes ?? '';
        // started_at llega en ISO con offset; se parte en fecha y hora locales.
        const when = new Date(a.started_at);
        const p = (n: number) => `${n}`.padStart(2, '0');
        this.date = `${when.getFullYear()}-${p(when.getMonth() + 1)}-${p(when.getDate())}`;
        this.time = `${p(when.getHours())}:${p(when.getMinutes())}`;
        this.targetDate = this.date;
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar la actividad', 'OK');
        this.router.navigate(['/log']);
      },
    });
  }

  onSportChange(value: string): void {
    this.sportName = value;
    this.sportSignal.set(value);
  }

  useSuggestion(name: string): void {
    this.onSportChange(name);
  }

  /** Misma heurística que el backend, para previsualizar el color al teclear. */
  private guessFamily(name: string): string {
    const t = name
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase();
    if (!t) return 'other';
    const map: [string, string[]][] = [
      ['strength', ['fuerza', 'pesas', 'gimnasio', 'gym', 'calistenia', 'circuit', 'crossfit', 'functional']],
      ['racket', ['padel', 'tenis', 'squash', 'badminton', 'futbol', 'baloncesto', 'voleibol', 'hockey']],
      ['cardio', ['correr', 'carrera', 'running', 'bici', 'ciclismo', 'spinning', 'nadar', 'natacion', 'remo', 'eliptica', 'hiit', 'escalada', 'boxeo']],
      ['mobility', ['yoga', 'pilates', 'estiramiento', 'movilidad', 'caminar', 'andar', 'senderismo']],
    ];
    for (const [key, words] of map) {
      if (words.some((w) => t.includes(w))) return key;
    }
    return 'other';
  }

  setFamily(key: string): void {
    this.manualFamily.update((current) => (current === key ? null : key));
  }

  get canSave(): boolean {
    return this.sportName.trim().length > 0 && !this.saving();
  }

  save(): void {
    if (!this.canSave) return;
    this.saving.set(true);

    const body = {
        sport_name: this.sportName.trim(),
        activity_type: this.family()?.key,
        started_at: `${this.date}T${this.time || '12:00'}`,
        duration_min: this.durationMin ?? undefined,
        calories: this.calories ?? undefined,
        feeling: this.feeling ?? undefined,
      notes: this.notes.trim() || undefined,
    };

    const id = this.editingId();
    const peticion = id ? this.activities.update(id, body) : this.activities.create(body);

    peticion.subscribe({
      next: () => {
        this.snack.open(id ? 'Actividad actualizada' : 'Actividad registrada', 'OK', {
          duration: 2500,
        });
        this.goToDay();
      },
      error: (err) => {
        this.saving.set(false);
        this.snack.open(
          err?.error?.error ?? 'No se pudo guardar. Inténtalo de nuevo.',
          'OK',
          { duration: 6000 },
        );
      },
    });
  }

  /** Vuelve al día al que se ha añadido, como hace el registro de comidas. */
  private goToDay(): void {
    if (this.date === toISODate(new Date())) {
      this.router.navigate(['/log']);
    } else {
      this.router.navigate(['/calendar'], {
        queryParams: { mode: 'day', date: this.date },
      });
    }
  }

  cancel(): void {
    // Editando se vuelve al día; creando, a la pantalla de qué quieres añadir.
    if (this.editingId()) {
      this.goToDay();
      return;
    }
    this.router.navigate(['/add'], {
      queryParams: this.targetDate ? { date: this.targetDate } : {},
    });
  }
}
