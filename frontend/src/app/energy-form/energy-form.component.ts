import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { EnergyService } from '../services/energy.service';
import { fromISODate, toISODate } from '../shared/date.utils';

/**
 * Registro del gasto energético (calorías gastadas) de un día.
 *
 * A diferencia de la actividad, es un valor único por día: al abrir la pantalla
 * se carga lo que ya hubiera para ese día y guardar lo corrige en vez de
 * duplicarlo. Hoy es manual; el día que se conecte Whoop rellenará esto solo.
 */
@Component({
  selector: 'app-energy-form',
  standalone: true,
  imports: [FormsModule, MatIconModule, MatSnackBarModule],
  templateUrl: './energy-form.component.html',
  styleUrl: './energy-form.component.scss',
})
export class EnergyFormComponent implements OnInit {
  private energy = inject(EnergyService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private snack = inject(MatSnackBar);

  calories: number | null = null;
  note = '';
  date = '';

  /** Día al que se registra, arrastrado desde el calendario o el hub de añadir. */
  private targetDate: string | null = null;

  saving = signal(false);
  deleting = signal(false);
  loading = signal(true);
  /** Id de la entrada existente de ese día; habilita corregir y borrar. */
  existingId = signal<number | null>(null);
  /** Si el dato lo trajo Whoop: se avisa de que se sobrescribirá al editar. */
  fromWhoop = signal(false);

  ngOnInit(): void {
    this.targetDate = this.route.snapshot.queryParamMap.get('date');
    this.date = this.targetDate ?? toISODate(new Date());
    this.loadDay();
  }

  private loadDay(): void {
    this.loading.set(true);
    this.energy.getDay(this.date).subscribe({
      next: (res) => {
        if (res.entry) {
          this.existingId.set(res.entry.id);
          this.calories = res.entry.calories;
          this.note = res.entry.note ?? '';
          this.fromWhoop.set(res.entry.source === 'whoop');
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  get dayLabel(): string {
    return fromISODate(this.date).toLocaleDateString('es', {
      weekday: 'long', day: 'numeric', month: 'long',
    });
  }

  get canSave(): boolean {
    return this.calories != null && this.calories > 0 && !this.saving();
  }

  save(): void {
    if (!this.canSave) return;
    this.saving.set(true);

    this.energy
      .save({
        calories: this.calories!,
        measured_on: this.date,
        note: this.note.trim() || undefined,
      })
      .subscribe({
        next: () => {
          this.snack.open('Gasto guardado', 'OK', { duration: 2500 });
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

  remove(): void {
    const id = this.existingId();
    if (id == null || this.deleting()) return;
    this.deleting.set(true);
    this.energy.remove(id).subscribe({
      next: () => {
        this.snack.open('Gasto eliminado', 'OK', { duration: 2500 });
        this.goToDay();
      },
      error: () => {
        this.deleting.set(false);
        this.snack.open('No se pudo eliminar', 'OK');
      },
    });
  }

  /** Vuelve al detalle del día en el calendario, como el resto de registros. */
  private goToDay(): void {
    this.router.navigate(['/calendar'], {
      queryParams: { mode: 'day', date: this.date },
    });
  }

  cancel(): void {
    if (this.existingId()) {
      this.goToDay();
      return;
    }
    this.router.navigate(['/add'], {
      queryParams: this.targetDate ? { date: this.targetDate } : {},
    });
  }
}
