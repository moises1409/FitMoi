import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { BodyService } from '../services/body.service';
import {
  BodyMeasurement,
  BodyPhoto,
  MeasurementKey,
  MEASUREMENT_FIELDS,
  POSES,
} from '../models/body.model';
import { toISODate } from '../shared/date.utils';

type MeasKey = MeasurementKey;

@Component({
  selector: 'app-body-progress',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, MatIconModule, MatSnackBarModule, ThemeToggleComponent],
  templateUrl: './body-progress.component.html',
  styleUrl: './body-progress.component.scss',
})
export class BodyProgressComponent implements OnInit {
  private body = inject(BodyService);
  private snack = inject(MatSnackBar);

  readonly summary = this.body.summary;
  loading = signal(true);

  readonly fields = MEASUREMENT_FIELDS;
  readonly poses = POSES;

  // ── Formulario de medidas ──
  showMeasureForm = signal(false);
  savingMeasure = signal(false);
  measureDate = toISODate(new Date());
  measure: Record<MeasKey, number | null> = {
    waist_cm: null, abdomen_cm: null, chest_cm: null, biceps_cm: null,
  };
  measureNote = '';

  // ── Formulario de foto ──
  showPhotoForm = signal(false);
  savingPhoto = signal(false);
  photoDate = toISODate(new Date());
  photoPose = '';
  photoNote = '';
  photoFile: File | null = null;

  // ── Visor de foto a pantalla ──
  viewer = signal<BodyPhoto | null>(null);
  pendingPhotoDelete = signal<number | null>(null);
  pendingMeasureDelete = signal<number | null>(null);

  readonly measurements = computed(() => this.summary()?.measurements ?? null);
  readonly photos = computed(() => this.summary()?.photos ?? []);

  /** Tomas de la más reciente a la más antigua (para la lista). */
  readonly recentTakes = computed(() =>
    (this.measurements()?.entries ?? []).slice().reverse(),
  );

  /** Tendencia por contorno: actual, cambios y mini-gráfica de evolución. */
  readonly trends = computed(() => {
    const m = this.measurements();
    if (!m) return [];
    const entries = m.entries; // cronológico
    return this.fields
      .map(({ key, label }) => {
        const change = m.changes[key];
        if (!change) return null;
        const serie = entries
          .map((e) => e[key] as number | null)
          .filter((v): v is number => v !== null);
        return {
          key,
          label,
          current: change.current,
          change_last: change.change_last,
          change_total: change.change_total,
          points: serie.length >= 3 ? this.sparkline(serie) : '',
        };
      })
      .filter((t): t is NonNullable<typeof t> => t !== null);
  });

  /** Fotos agrupadas por fecha (periodo), de la más reciente a la más antigua. */
  readonly photosByDate = computed(() => {
    const groups = new Map<string, BodyPhoto[]>();
    for (const p of this.photos()) {
      const list = groups.get(p.taken_on) ?? [];
      list.push(p);
      groups.set(p.taken_on, list);
    }
    return [...groups.entries()]
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))
      .map(([date, items]) => ({ date, items }));
  });

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

  /** Valores presentes de una toma, con su etiqueta, para la lista del histórico. */
  valuesOf(entry: BodyMeasurement): { label: string; value: number }[] {
    return this.fields
      .map(({ key, label }) => ({ label, value: entry[key] as number | null }))
      .filter((v): v is { label: string; value: number } => v.value !== null);
  }

  ngOnInit(): void {
    this.body.load().subscribe({
      next: () => this.loading.set(false),
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar tu progreso', 'OK');
      },
    });
  }

  // ── Medidas ──
  saveMeasurement(): void {
    if (this.savingMeasure()) return;
    const payload: Record<string, unknown> = { measured_on: this.measureDate };
    for (const { key } of this.fields) {
      const v = this.measure[key as MeasKey];
      if (v !== null && v !== undefined && `${v}` !== '') payload[key] = v;
    }
    if (this.measureNote.trim()) payload['note'] = this.measureNote.trim();
    if (Object.keys(payload).length <= 1 && !this.measureNote.trim()) {
      this.snack.open('Indica al menos una medida', 'OK');
      return;
    }
    this.savingMeasure.set(true);
    this.body.addMeasurement(payload).subscribe({
      next: () => {
        this.savingMeasure.set(false);
        this.showMeasureForm.set(false);
        this.measure = { waist_cm: null, abdomen_cm: null, chest_cm: null, biceps_cm: null };
        this.measureNote = '';
        this.snack.open('Medidas registradas', 'OK', { duration: 2500 });
      },
      error: (err) => {
        this.savingMeasure.set(false);
        this.snack.open(err?.error?.error ?? 'No se pudo guardar', 'OK', { duration: 5000 });
      },
    });
  }

  requestMeasureDelete(entry: BodyMeasurement): void {
    if (this.pendingMeasureDelete() === entry.id) {
      this.body.deleteMeasurement(entry.id).subscribe({
        next: () => {
          this.pendingMeasureDelete.set(null);
          this.snack.open('Toma eliminada', 'OK', { duration: 2500 });
        },
        error: () => this.snack.open('No se pudo eliminar', 'OK'),
      });
      return;
    }
    this.pendingMeasureDelete.set(entry.id);
    setTimeout(() => {
      if (this.pendingMeasureDelete() === entry.id) this.pendingMeasureDelete.set(null);
    }, 4000);
  }

  // ── Fotos ──
  onPhotoSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.photoFile = input.files?.[0] ?? null;
  }

  savePhoto(): void {
    if (this.savingPhoto()) return;
    if (!this.photoFile) {
      this.snack.open('Elige una foto', 'OK');
      return;
    }
    this.savingPhoto.set(true);
    this.body.addPhoto(this.photoFile, this.photoDate, this.photoPose || undefined, this.photoNote)
      .subscribe({
        next: () => {
          this.savingPhoto.set(false);
          this.showPhotoForm.set(false);
          this.photoFile = null;
          this.photoPose = '';
          this.photoNote = '';
          this.snack.open('Foto guardada', 'OK', { duration: 2500 });
        },
        error: (err) => {
          this.savingPhoto.set(false);
          this.snack.open(err?.error?.error ?? 'No se pudo subir la foto', 'OK', { duration: 5000 });
        },
      });
  }

  requestPhotoDelete(photo: BodyPhoto): void {
    if (this.pendingPhotoDelete() === photo.id) {
      this.body.deletePhoto(photo.id).subscribe({
        next: () => {
          this.pendingPhotoDelete.set(null);
          if (this.viewer()?.id === photo.id) this.viewer.set(null);
          this.snack.open('Foto eliminada', 'OK', { duration: 2500 });
        },
        error: () => this.snack.open('No se pudo eliminar', 'OK'),
      });
      return;
    }
    this.pendingPhotoDelete.set(photo.id);
    setTimeout(() => {
      if (this.pendingPhotoDelete() === photo.id) this.pendingPhotoDelete.set(null);
    }, 4000);
  }

  poseLabel(value: string | null): string {
    return this.poses.find((p) => p.value === value)?.label ?? '';
  }
}
