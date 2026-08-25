import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivityService } from '../services/activity.service';
import { Activity, FEELING_LABELS } from '../models/activity.model';
import { toISODate } from '../shared/date.utils';

const CONFIRM_WINDOW_MS = 4000;

/** Una fila del bloque de métricas de Whoop, ya lista para pintar. */
interface MetricRow {
  icon: string;
  label: string;
  value: string;
}

/** Una zona de pulso: minutos dentro de ella y su peso sobre el total. */
interface HeartZone {
  label: string;
  minutes: number;
  pct: number;
  color: string;
}

// Whoop reparte la sesión en seis zonas de pulso (0-5). Del frío al rojo, para
// que la barra se lea de un vistazo: cuanto más a la derecha, más intensa.
const ZONE_COLORS = ['#94A3B8', '#0891B2', '#22A0B8', '#65A30D', '#D97706', '#DC2626'];
const ZONE_KEYS = [
  'zone_zero_milli',
  'zone_one_milli',
  'zone_two_milli',
  'zone_three_milli',
  'zone_four_milli',
  'zone_five_milli',
];

/**
 * Detalle de una actividad. Además de lo que ya se ve en la ficha del día,
 * saca a la luz lo que trae la pulsera (strain, pulso medio/máximo, distancia y
 * las zonas de pulso) que hasta ahora se guardaba en `metrics` sin mostrarse.
 */
@Component({
  selector: 'app-activity-detail',
  standalone: true,
  imports: [DatePipe, DecimalPipe, MatIconModule, MatSnackBarModule],
  templateUrl: './activity-detail.component.html',
  styleUrl: './activity-detail.component.scss',
})
export class ActivityDetailComponent implements OnInit {
  private activities = inject(ActivityService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private snack = inject(MatSnackBar);

  readonly feelingLabels = FEELING_LABELS;

  activity = signal<Activity | null>(null);
  loading = signal(true);
  notFound = signal(false);
  pendingDelete = signal(false);
  private timer?: ReturnType<typeof setTimeout>;

  /** Métricas de la pulsera, solo las que vienen con valor. */
  readonly metricRows = computed<MetricRow[]>(() => {
    const a = this.activity();
    if (!a || a.source !== 'whoop') return [];
    const m = a.metrics ?? {};
    const rows: MetricRow[] = [];

    const strain = this.num(m['strain']);
    if (strain !== null) {
      rows.push({ icon: 'bolt', label: 'Strain', value: strain.toFixed(1) });
    }
    const avg = this.num(m['average_heart_rate']);
    if (avg !== null) {
      rows.push({ icon: 'favorite', label: 'Pulso medio', value: `${Math.round(avg)} ppm` });
    }
    const max = this.num(m['max_heart_rate']);
    if (max !== null) {
      rows.push({ icon: 'monitor_heart', label: 'Pulso máximo', value: `${Math.round(max)} ppm` });
    }
    const dist = this.num(m['distance_meter']);
    if (dist !== null && dist > 0) {
      const value = dist >= 1000 ? `${(dist / 1000).toFixed(2)} km` : `${Math.round(dist)} m`;
      rows.push({ icon: 'straighten', label: 'Distancia', value });
    }
    const alt = this.num(m['altitude_gain_meter']);
    if (alt !== null && alt > 0) {
      rows.push({ icon: 'terrain', label: 'Desnivel', value: `${Math.round(alt)} m` });
    }
    const pct = this.num(m['percent_recorded']);
    if (pct !== null && pct < 100) {
      rows.push({ icon: 'sensors', label: 'Registrado', value: `${Math.round(pct)}%` });
    }
    return rows;
  });

  /** Zonas de pulso normalizadas a minutos y porcentaje sobre el total. */
  readonly heartZones = computed<HeartZone[]>(() => {
    const a = this.activity();
    if (!a || a.source !== 'whoop') return [];
    const raw = (a.metrics ?? {})['zone_durations'] as Record<string, unknown> | undefined;
    if (!raw || typeof raw !== 'object') return [];

    const millis = ZONE_KEYS.map((k) => this.num(raw[k]) ?? 0);
    const total = millis.reduce((sum, v) => sum + v, 0);
    if (total <= 0) return [];

    return millis.map((ms, i) => ({
      label: `Zona ${i}`,
      minutes: Math.round(ms / 60000),
      pct: Math.round((ms / total) * 100),
      color: ZONE_COLORS[i],
    }));
  });

  readonly hasZones = computed(() => this.heartZones().length > 0);

  ngOnInit(): void {
    this.activities.ensureFamilies().subscribe();
    const id = this.route.snapshot.queryParamMap.get('id');
    if (!id) {
      this.notFound.set(true);
      this.loading.set(false);
      return;
    }
    this.activities.get(Number(id)).subscribe({
      next: (a) => {
        this.activity.set(a);
        this.loading.set(false);
      },
      error: () => {
        this.notFound.set(true);
        this.loading.set(false);
      },
    });
  }

  colorOf(family: string): string {
    return this.activities.colorOf(family);
  }

  labelOf(family: string): string {
    return this.activities.familyOf(family)?.label ?? 'Otro';
  }

  iconOf(family: string): string {
    return this.activities.familyOf(family)?.icon ?? 'sports';
  }

  /** Vuelve al día de la actividad en el calendario. */
  back(): void {
    const a = this.activity();
    if (!a) {
      this.router.navigate(['/calendar']);
      return;
    }
    this.router.navigate(['/calendar'], {
      queryParams: { mode: 'day', date: toISODate(new Date(a.started_at)) },
    });
  }

  edit(): void {
    const a = this.activity();
    if (a) this.router.navigate(['/activity'], { queryParams: { id: a.id } });
  }

  /** Primer toque arma la confirmación; el segundo borra. */
  requestDelete(): void {
    if (this.pendingDelete()) {
      this.confirmDelete();
      return;
    }
    clearTimeout(this.timer);
    this.pendingDelete.set(true);
    this.timer = setTimeout(() => this.pendingDelete.set(false), CONFIRM_WINDOW_MS);
  }

  cancelDelete(): void {
    clearTimeout(this.timer);
    this.pendingDelete.set(false);
  }

  private confirmDelete(): void {
    const a = this.activity();
    if (!a) return;
    this.cancelDelete();
    this.activities.remove(a.id).subscribe({
      next: () => {
        this.snack.open('Actividad eliminada', 'OK', { duration: 2500 });
        this.back();
      },
      error: () => this.snack.open('No se pudo eliminar', 'OK'),
    });
  }

  /** Convierte a número lo que pueda venir de un JSON (o null si no cuela). */
  private num(value: unknown): number | null {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
}
