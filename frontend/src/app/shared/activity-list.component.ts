import { Component, EventEmitter, Input, Output, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivityService } from '../services/activity.service';
import { Activity, FEELING_LABELS } from '../models/activity.model';

const CONFIRM_WINDOW_MS = 4000;

/**
 * Ficha de actividad con sus acciones. Vive aparte porque la comparten la
 * pantalla de Hoy y el detalle del día en el Calendario; duplicar la plantilla
 * y la lógica de borrado en las dos habría sido pedir que se desincronizaran.
 */
@Component({
  selector: 'app-activity-list',
  standalone: true,
  imports: [DatePipe, DecimalPipe, RouterLink, MatIconModule, MatSnackBarModule],
  template: `
    @for (a of activities; track a.id) {
      <div class="activity-card card">
        <span class="activity-bar" [style.background]="colorOf(a.activity_type)"></span>
        <div class="activity-body">
          <a class="activity-open" [routerLink]="['/activity/detail']" [queryParams]="{ id: a.id }"
             aria-label="Ver detalle de la actividad">
            <div class="activity-head">
              <mat-icon class="activity-icon" [style.color]="colorOf(a.activity_type)">
                {{ iconOf(a.activity_type) }}
              </mat-icon>
              <span class="activity-name">{{ a.sport_name }}</span>
              @if (a.duration_min) {
                <span class="activity-dur">{{ a.duration_min }} min</span>
              }
              <mat-icon class="activity-chevron">chevron_right</mat-icon>
            </div>

            <p class="activity-meta">
              {{ labelOf(a.activity_type) }}
              · {{ a.started_at | date:'HH:mm' }}
              @if (a.calories) { · {{ a.calories | number:'1.0-0' }} kcal }
              @if (a.feeling) { · {{ feelingLabels[a.feeling] }} }
              @if (a.source === 'whoop') { · <span class="from-whoop">Whoop</span> }
            </p>

            @if (a.notes) { <p class="activity-notes">{{ a.notes }}</p> }
          </a>

          <div class="activity-actions">
            @if (pendingDelete() === a.id) {
              <button class="act-confirm" type="button" (click)="requestDelete(a)">
                <mat-icon>delete_forever</mat-icon>
                Eliminar
              </button>
              <button class="act-cancel" type="button" (click)="cancelDelete()">Cancelar</button>
            } @else {
              @if (a.source === 'manual') {
                <a class="act-btn" [routerLink]="['/activity']" [queryParams]="{ id: a.id }">
                  <mat-icon>edit</mat-icon> Editar
                </a>
              } @else {
                <span class="act-locked">
                  <mat-icon>lock</mat-icon> Se sincroniza desde Whoop
                </span>
              }
              <button class="act-btn danger" type="button" (click)="requestDelete(a)">
                <mat-icon>delete_outline</mat-icon> Eliminar
              </button>
            }
          </div>
        </div>
      </div>
    } @empty {
      <p class="no-activity">Sin actividad registrada este día.</p>
    }
  `,
  styleUrl: './activity-list.component.scss',
})
export class ActivityListComponent {
  private activityService = inject(ActivityService);
  private snack = inject(MatSnackBar);

  constructor() {
    // La ficha necesita el color, el icono y el nombre de la familia; se los
    // pide ella misma para no depender de que la pantalla se acuerde.
    this.activityService.ensureFamilies().subscribe();
  }

  @Input() activities: Activity[] = [];
  /** Avisa a la pantalla para que recargue el día. */
  @Output() changed = new EventEmitter<void>();

  readonly feelingLabels = FEELING_LABELS;
  pendingDelete = signal<number | null>(null);
  private timer?: ReturnType<typeof setTimeout>;

  colorOf(family: string): string {
    return this.activityService.colorOf(family);
  }

  labelOf(family: string): string {
    return this.activityService.familyOf(family)?.label ?? 'Otro';
  }

  iconOf(family: string): string {
    return this.activityService.familyOf(family)?.icon ?? 'sports';
  }

  /** Primer toque arma la confirmación; el segundo borra. */
  requestDelete(activity: Activity): void {
    if (this.pendingDelete() === activity.id) {
      this.confirmDelete(activity);
      return;
    }
    clearTimeout(this.timer);
    this.pendingDelete.set(activity.id);
    this.timer = setTimeout(() => this.pendingDelete.set(null), CONFIRM_WINDOW_MS);
  }

  cancelDelete(): void {
    clearTimeout(this.timer);
    this.pendingDelete.set(null);
  }

  private confirmDelete(activity: Activity): void {
    this.cancelDelete();
    this.activityService.remove(activity.id).subscribe({
      next: () => {
        this.snack.open('Actividad eliminada', 'OK', { duration: 2500 });
        this.changed.emit();
      },
      error: () => this.snack.open('No se pudo eliminar', 'OK'),
    });
  }
}
