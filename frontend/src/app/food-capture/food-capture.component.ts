import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { FoodService } from '../services/food.service';
import { EntryDraftService } from '../services/entry-draft.service';
import { FoodAnalysis } from '../models/food.model';

/** El backend reduce la imagen antes de enviarla a Claude; esto solo evita
 *  subir ficheros absurdamente grandes por la red local. */
const MAX_UPLOAD_BYTES = 16 * 1024 * 1024;
/** Debe coincidir con MAX_PHOTOS del backend. */
const MAX_PHOTOS = 4;

interface Shot {
  file: File;
  preview: string;
}

@Component({
  selector: 'app-food-capture',
  standalone: true,
  imports: [FormsModule, RouterLink, MatIconModule, MatSnackBarModule],
  templateUrl: './food-capture.component.html',
  styleUrl: './food-capture.component.scss',
})
export class FoodCaptureComponent {
  private foodService = inject(FoodService);
  private drafts = inject(EntryDraftService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private snack = inject(MatSnackBar);

  /** Día al que se añade, arrastrado desde /add cuando no es hoy. */
  private targetDate = this.route.snapshot.queryParamMap.get('date');

  readonly maxPhotos = MAX_PHOTOS;
  shots = signal<Shot[]>([]);
  analyzing = signal(false);
  /** Descripción opcional que acompaña a las fotos y las matiza. */
  description = '';

  get canAddMore(): boolean {
    return this.shots().length < MAX_PHOTOS;
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    // Se limpia para que volver a elegir el mismo fichero dispare change.
    input.value = '';
    if (!files.length) return;

    const free = MAX_PHOTOS - this.shots().length;
    if (files.length > free) {
      this.snack.open(`Máximo ${MAX_PHOTOS} imágenes; se añaden las primeras`, 'OK', {
        duration: 4000,
      });
    }

    for (const file of files.slice(0, free)) {
      if (!file.type.startsWith('image/')) {
        this.snack.open('Solo se permiten imágenes', 'OK');
        continue;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        this.snack.open(`"${file.name}" es demasiado grande (máx. 16 MB)`, 'OK', { duration: 5000 });
        continue;
      }

      const reader = new FileReader();
      reader.onload = (e) =>
        this.shots.update((list) => [...list, { file, preview: e.target?.result as string }]);
      reader.onerror = () => this.snack.open('No se pudo leer la imagen', 'OK');
      reader.readAsDataURL(file);
    }
  }

  removeShot(index: number): void {
    this.shots.update((list) => list.filter((_, i) => i !== index));
  }

  clearAll(): void {
    this.shots.set([]);
    this.description = '';
  }

  analyze(): void {
    const shots = this.shots();
    if (!shots.length || this.analyzing()) return;
    this.analyzing.set(true);

    this.foodService.analyzePhotos(shots.map((s) => s.file), this.description).subscribe({
      next: (result: FoodAnalysis) => {
        this.analyzing.set(false);
        this.drafts.fromAnalysis(result, this.targetDate);
        this.router.navigate(['/confirm']);
      },
      error: (err) => {
        this.analyzing.set(false);
        let msg = 'Error de conexión. Verifica que el backend esté corriendo.';
        if (err.status === 503) msg = err.error?.error ?? 'API key de Anthropic no configurada.';
        else if (err.status === 400) msg = err.error?.error ?? 'Imagen inválida.';
        else if (err.status === 502) msg = err.error?.error ?? 'El análisis falló. Inténtalo de nuevo.';
        else if (err.status === 413) msg = 'Las imágenes son demasiado grandes.';
        else if (err.status > 0) msg = err.error?.error ?? `Error del servidor (${err.status}).`;
        this.snack.open(msg, 'OK', { duration: 8000 });
      },
    });
  }
}
