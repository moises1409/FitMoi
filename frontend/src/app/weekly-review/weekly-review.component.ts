import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { ReviewService } from '../services/review.service';
import {
  TENDENCIA_ICONS,
  TENDENCIA_LABELS,
  Tendencia,
  WeeklyReviewListItem,
  WeeklyReviewResponse,
} from '../models/review.model';
import { addDays, fromISODate, startOfWeek, toISODate } from '../shared/date.utils';

@Component({
  selector: 'app-weekly-review',
  standalone: true,
  imports: [DatePipe, DecimalPipe, MatIconModule, MatSnackBarModule, ThemeToggleComponent],
  templateUrl: './weekly-review.component.html',
  styleUrl: './weekly-review.component.scss',
})
export class WeeklyReviewComponent implements OnInit {
  private reviews = inject(ReviewService);
  private snack = inject(MatSnackBar);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  /** Cualquier día de la semana que se está viendo. */
  readonly anchor = signal<Date>(new Date());
  readonly data = signal<WeeklyReviewResponse | null>(null);
  readonly history = signal<WeeklyReviewListItem[]>([]);

  loading = signal(true);
  generating = signal(false);

  readonly tendenciaLabels = TENDENCIA_LABELS;
  readonly tendenciaIcons = TENDENCIA_ICONS;

  /** Lunes de la semana mostrada. */
  readonly monday = computed(() => startOfWeek(this.anchor()));

  /** No se puede avanzar más allá de la semana en curso. */
  readonly canGoNext = computed(() => startOfWeek(addDays(this.anchor(), 7)) <= startOfWeek(new Date()));

  readonly isCurrentWeek = computed(() =>
    toISODate(this.monday()) === toISODate(startOfWeek(new Date())),
  );

  /** Histórico sin la semana que se está viendo: ya se muestra arriba. */
  readonly otherWeeks = computed(() => {
    const shown = this.data()?.week.week_start;
    return this.history().filter((w) => w.week_start !== shown);
  });

  ngOnInit(): void {
    const iso = this.route.snapshot.queryParamMap.get('date');
    if (iso) this.anchor.set(fromISODate(iso));
    this.load();
    this.loadHistory();
  }

  private load(): void {
    this.loading.set(true);
    this.reviews.getWeekly(toISODate(this.anchor())).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar el resumen', 'OK', { duration: 4000 });
      },
    });
  }

  private loadHistory(): void {
    this.reviews.list().subscribe({
      next: (res) => this.history.set(res.items),
      error: () => {},
    });
  }

  private navigateTo(date: Date): void {
    this.anchor.set(date);
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { date: toISODate(date) },
      replaceUrl: true,
    });
    this.load();
  }

  shiftWeek(direction: number): void {
    if (direction > 0 && !this.canGoNext()) return;
    this.navigateTo(addDays(this.anchor(), direction * 7));
  }

  goToCurrentWeek(): void {
    this.navigateTo(new Date());
  }

  openWeek(item: WeeklyReviewListItem): void {
    this.navigateTo(fromISODate(item.week_start));
    if (typeof window !== 'undefined') window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  /** Genera (o regenera) el resumen de la semana mostrada. */
  generate(): void {
    if (this.generating()) return;
    this.generating.set(true);
    this.reviews.regenerate(toISODate(this.anchor())).subscribe({
      next: (res) => {
        this.data.set(res);
        this.generating.set(false);
        this.loadHistory();
        this.snack.open('Resumen generado', 'OK', { duration: 2500 });
      },
      error: (err) => {
        this.generating.set(false);
        this.snack.open(err?.error?.error ?? 'No se pudo generar el resumen', 'OK', {
          duration: 5000,
        });
      },
    });
  }

  trendClass(t: Tendencia): string {
    return `trend-${t}`;
  }

  trackWeek(_i: number, item: WeeklyReviewListItem): string {
    return item.week_start;
  }
}
