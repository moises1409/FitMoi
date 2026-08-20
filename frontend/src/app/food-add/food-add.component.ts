import { Component, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe, NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { Subject, debounceTime, distinctUntilChanged, switchMap } from 'rxjs';
import { LibraryService } from '../services/library.service';
import { EntryDraftService } from '../services/entry-draft.service';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { FoodTemplate, MEAL_TYPES, detectMealType } from '../models/food.model';
import { fromISODate, isSameDay, toISODate } from '../shared/date.utils';

@Component({
  selector: 'app-food-add',
  standalone: true,
  imports: [
    DecimalPipe,
    NgTemplateOutlet,
    FormsModule,
    RouterLink,
    MatIconModule,
    MatSnackBarModule,
    ThemeToggleComponent,
  ],
  templateUrl: './food-add.component.html',
  styleUrl: './food-add.component.scss',
})
export class FoodAddComponent implements OnInit {
  private library = inject(LibraryService);
  private drafts = inject(EntryDraftService);
  private snack = inject(MatSnackBar);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  query = '';
  loading = signal(true);
  searching = signal(false);
  suggested = signal<FoodTemplate[]>([]);
  recent = signal<FoodTemplate[]>([]);
  results = signal<FoodTemplate[] | null>(null);

  /** Día al que se está añadiendo; por defecto hoy. Llega como ?date=. */
  targetDate = signal<string | null>(null);

  readonly mealSlot = detectMealType();
  private search$ = new Subject<string>();

  ngOnInit(): void {
    const date = this.route.snapshot.queryParamMap.get('date');
    if (date && !isSameDay(fromISODate(date), new Date())) this.targetDate.set(date);

    this.library.suggest(this.mealSlot).subscribe({
      next: (res) => {
        this.suggested.set(res.suggested);
        this.recent.set(res.recent);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('No se pudo cargar tu biblioteca', 'OK');
      },
    });

    this.search$
      .pipe(
        debounceTime(220),
        distinctUntilChanged(),
        switchMap((q) => {
          this.searching.set(true);
          return this.library.search(q);
        }),
      )
      .subscribe({
        next: (res) => {
          this.results.set(res.items);
          this.searching.set(false);
        },
        error: () => this.searching.set(false),
      });
  }

  get slotLabel(): string {
    const label = MEAL_TYPES.find((m) => m.value === this.mealSlot)?.label ?? '';
    return `Sueles tomar a esta hora · ${label}`;
  }

  /** Etiqueta del día destino cuando no es hoy, para que quede claro. */
  get targetLabel(): string {
    const date = this.targetDate();
    return date
      ? fromISODate(date).toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' })
      : '';
  }

  /** Parámetros que arrastran el día destino a foto y descripción. */
  get dateParams(): Record<string, string> {
    const date = this.targetDate();
    return date ? { date } : {};
  }

  /** Igual, más el texto buscado, para "analizar «X» con IA". */
  get describeParams(): Record<string, string> {
    return { ...this.dateParams, q: this.query };
  }

  onQueryChange(value: string): void {
    this.query = value;
    if (!value.trim()) {
      this.results.set(null);
      this.searching.set(false);
      return;
    }
    this.search$.next(value.trim());
  }

  clearQuery(): void {
    this.onQueryChange('');
  }

  trackTemplate(_index: number, template: FoodTemplate): number {
    return template.id;
  }

  /** Un toque: prepara el borrador y va directo a confirmar. */
  add(template: FoodTemplate): void {
    this.drafts.fromTemplate(template, this.targetDate() ?? toISODate(new Date()));
    this.router.navigate(['/confirm']);
  }
}
