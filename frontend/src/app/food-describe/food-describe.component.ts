import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { EntryDraftService } from '../services/entry-draft.service';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';

const EXAMPLES = [
  'Dos huevos revueltos con una tostada integral y aguacate',
  'Plato de lentejas con chorizo, ración normal',
  'Café con leche desnatada y un croissant',
];

@Component({
  selector: 'app-food-describe',
  standalone: true,
  imports: [FormsModule, RouterLink, MatIconModule, MatSnackBarModule, ThemeToggleComponent],
  templateUrl: './food-describe.component.html',
  styleUrl: './food-describe.component.scss',
})
export class FoodDescribeComponent implements OnInit {
  private foodService = inject(FoodService);
  private drafts = inject(EntryDraftService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private snack = inject(MatSnackBar);

  description = '';
  analyzing = signal(false);
  readonly examples = EXAMPLES;

  ngOnInit(): void {
    // Llega precargado desde "Analizar «X» con IA" cuando la búsqueda no encuentra nada.
    const q = this.route.snapshot.queryParamMap.get('q');
    if (q) this.description = q;
  }

  useExample(text: string): void {
    this.description = text;
  }

  get canAnalyze(): boolean {
    return this.description.trim().length >= 3 && !this.analyzing();
  }

  analyze(): void {
    if (!this.canAnalyze) return;
    this.analyzing.set(true);

    this.foodService.analyzeText(this.description).subscribe({
      next: (analysis) => {
        this.analyzing.set(false);
        this.drafts.fromAnalysis(analysis, this.route.snapshot.queryParamMap.get('date'));
        this.router.navigate(['/confirm']);
      },
      error: (err) => {
        this.analyzing.set(false);
        const msg =
          err.status === 503
            ? (err.error?.error ?? 'API key de Anthropic no configurada.')
            : (err.error?.error ?? 'No se pudo analizar la descripción. Inténtalo de nuevo.');
        this.snack.open(msg, 'OK', { duration: 8000 });
      },
    });
  }

  goBack(): void {
    this.router.navigate(['/add']);
  }
}
