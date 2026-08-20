import { Component, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { LibraryService } from '../services/library.service';
import { ThemeToggleComponent } from '../shared/theme-toggle.component';
import { Assessment, FoodItem, FoodTemplate, MACRO_FIELDS } from '../models/food.model';

@Component({
  selector: 'app-food-library',
  standalone: true,
  imports: [
    DecimalPipe,
    FormsModule,
    RouterLink,
    MatIconModule,
    MatSnackBarModule,
    ThemeToggleComponent,
  ],
  templateUrl: './food-library.component.html',
  styleUrl: './food-library.component.scss',
})
export class FoodLibraryComponent implements OnInit {
  private library = inject(LibraryService);
  private snack = inject(MatSnackBar);

  readonly macroFields = MACRO_FIELDS;

  items = signal<FoodTemplate[]>([]);
  loading = signal(true);
  query = '';

  /** Id de la ficha desplegada; solo una a la vez. */
  expanded = signal<number | null>(null);
  reanalyzing = signal<number | null>(null);

  editing = signal<number | null>(null);
  draft = signal<Partial<FoodTemplate> & { portion_summary?: string }>({});
  uploading = signal<number | null>(null);

  /** Id origen de una fusión pendiente: el siguiente elegido es el destino. */
  mergeSource = signal<FoodTemplate | null>(null);
  pendingDelete = signal<number | null>(null);
  private deleteTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.library.search(this.query, 200).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.snack.open('Error cargando la biblioteca', 'OK');
      },
    });
  }

  trackItem(_index: number, item: FoodTemplate): number {
    return item.id;
  }

  // ── Ficha de detalle ──
  toggle(item: FoodTemplate): void {
    this.expanded.update((current) => (current === item.id ? null : item.id));
  }

  /** La valoración del LLM, si este alimento llegó a analizarse. */
  assessmentOf(item: FoodTemplate): Assessment | null {
    const a = item.analysis.assessment;
    if (!a) return null;
    const has = a.summary || a.positives?.length || a.concerns?.length || a.tip;
    return has ? { ...a, positives: a.positives ?? [], concerns: a.concerns ?? [] } : null;
  }

  hasAnalysis(item: FoodTemplate): boolean {
    return !!(this.assessmentOf(item) || item.analysis.portion_summary);
  }

  /** Recalcula macros y valoración con la foto guardada. */
  reanalyze(item: FoodTemplate): void {
    if (this.reanalyzing()) return;
    this.reanalyzing.set(item.id);

    this.library.reanalyze(item.id).subscribe({
      next: (updated) => {
        this.reanalyzing.set(null);
        this.items.update((list) => list.map((i) => (i.id === updated.id ? updated : i)));
        this.snack.open(
          updated.logs_updated
            ? `Reanalizado · ${updated.logs_updated} ${updated.logs_updated === 1 ? 'día corregido' : 'días corregidos'}`
            : 'Reanalizado',
          'OK',
          { duration: 4000 },
        );
      },
      error: (err) => {
        this.reanalyzing.set(null);
        this.snack.open(
          err?.error?.error ?? 'No se pudo reanalizar. Inténtalo de nuevo.',
          'OK',
          { duration: 6000 },
        );
      },
    });
  }

  onQueryChange(value: string): void {
    this.query = value;
    this.load();
  }

  // ── Edición ──
  startEdit(item: FoodTemplate): void {
    this.cancelMerge();
    this.editing.set(item.id);
    this.draft.set({
      name: item.name,
      quantity_label: item.quantity_label,
      calories: item.calories,
      proteins: item.proteins,
      carbs: item.carbs,
      fats: item.fats,
      fiber: item.fiber,
      saturated_fat: item.saturated_fat,
      salt: item.salt,
      // Copia profunda: editar porciones no debe tocar la fila hasta guardar.
      components: (item.components ?? []).map((c) => ({ ...c })),
      portion_summary: item.analysis.portion_summary ?? '',
    });
  }

  // ── Porciones (desglose por alimento) ──
  draftComponents(): FoodItem[] {
    return this.draft().components ?? [];
  }

  /** Suma de calorías del desglose, para poder cuadrarla con el total. */
  componentsTotal(): number {
    return Math.round(
      this.draftComponents().reduce((sum, c) => sum + (Number(c.calories) || 0), 0),
    );
  }

  patchComponent(index: number, key: 'name' | 'grams' | 'calories', value: unknown): void {
    const next = this.draftComponents().map((c, i) => {
      if (i !== index) return c;
      if (key === 'name') return { ...c, name: String(value) };
      const n = Number(value);
      const safe = Number.isFinite(n) && n > 0 ? Math.round(n * 10) / 10 : 0;
      // quantity se recalcula del peso: si no, quedaría el texto antiguo.
      return key === 'grams'
        ? { ...c, grams: safe, quantity: safe ? `~${Math.round(safe)} g` : '' }
        : { ...c, calories: Math.round(safe) };
    });
    this.patchDraft('components', next);
  }

  addComponent(): void {
    this.patchDraft('components', [
      ...this.draftComponents(),
      { name: '', quantity: '', grams: 0, calories: 0 },
    ]);
  }

  removeComponent(index: number): void {
    this.patchDraft('components', this.draftComponents().filter((_, i) => i !== index));
  }

  /** Cuadra las calorías totales con la suma de las porciones. */
  applySum(): void {
    this.patchDraft('calories', this.componentsTotal());
  }

  patchDraft(key: string, value: unknown): void {
    this.draft.update((d) => ({ ...d, [key]: value }));
  }

  cancelEdit(): void {
    this.editing.set(null);
    this.draft.set({});
  }

  saveEdit(item: FoodTemplate): void {
    this.library.update(item.id, this.draft()).subscribe({
      next: (updated) => {
        this.items.update((list) => list.map((i) => (i.id === updated.id ? updated : i)));
        this.cancelEdit();
        this.snack.open(this.updateMessage(updated.logs_updated), 'OK', { duration: 4000 });
      },
      error: (err) =>
        this.snack.open(err?.error?.error ?? 'No se pudo guardar', 'OK', { duration: 5000 }),
    });
  }

  /** Deja claro que el cambio ha reescrito días del historial. */
  private updateMessage(logs: number): string {
    if (!logs) return 'Actualizado';
    return logs === 1
      ? 'Actualizado · 1 día del historial corregido'
      : `Actualizado · ${logs} días del historial corregidos`;
  }

  // ── Imagen ──
  onPhotoSelected(item: FoodTemplate, event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      this.snack.open('Solo se permiten imágenes', 'OK');
      return;
    }

    this.uploading.set(item.id);
    this.library.setPhoto(item.id, file).subscribe({
      next: (updated) => {
        this.uploading.set(null);
        this.items.update((list) => list.map((i) => (i.id === updated.id ? updated : i)));
        this.snack.open(this.updateMessage(updated.logs_updated), 'OK', { duration: 4000 });
      },
      error: (err) => {
        this.uploading.set(null);
        this.snack.open(err?.error?.error ?? 'No se pudo subir la imagen', 'OK', { duration: 5000 });
      },
    });
  }

  removePhoto(item: FoodTemplate): void {
    this.library.clearPhoto(item.id).subscribe({
      next: (updated) => {
        this.items.update((list) => list.map((i) => (i.id === updated.id ? updated : i)));
        this.snack.open('Imagen eliminada', 'OK', { duration: 2500 });
      },
      error: () => this.snack.open('No se pudo eliminar la imagen', 'OK'),
    });
  }

  // ── Fusión de duplicados ──
  startMerge(item: FoodTemplate): void {
    this.cancelEdit();
    this.mergeSource.set(item);
    this.snack.open(`Elige con cuál fusionar «${item.name}»`, 'Cancelar', { duration: 6000 })
      .onAction()
      .subscribe(() => this.cancelMerge());
  }

  cancelMerge(): void {
    this.mergeSource.set(null);
  }

  completeMerge(target: FoodTemplate): void {
    const source = this.mergeSource();
    if (!source || source.id === target.id) return;

    this.library.merge(source.id, target.id).subscribe({
      next: () => {
        this.cancelMerge();
        this.snack.open(`Fusionado en «${target.name}»`, 'OK', { duration: 3000 });
        this.load();
      },
      error: () => {
        this.cancelMerge();
        this.snack.open('No se pudo fusionar', 'OK');
      },
    });
  }

  // ── Borrado ──
  /** Primer toque muestra la confirmación explícita; el segundo borra. */
  requestDelete(item: FoodTemplate): void {
    if (this.pendingDelete() === item.id) {
      this.confirmDelete(item);
      return;
    }
    clearTimeout(this.deleteTimer);
    this.pendingDelete.set(item.id);
    this.deleteTimer = setTimeout(() => {
      if (this.pendingDelete() === item.id) this.pendingDelete.set(null);
    }, 6000);
  }

  cancelDelete(): void {
    clearTimeout(this.deleteTimer);
    this.pendingDelete.set(null);
  }

  private confirmDelete(item: FoodTemplate): void {
    this.cancelDelete();
    this.library.remove(item.id).subscribe({
      next: (res) => {
        this.items.update((list) => list.filter((i) => i.id !== item.id));
        this.snack.open(
          res.logs_unlinked
            ? `Eliminado. Tus ${res.logs_unlinked} registros con este alimento se conservan.`
            : 'Eliminado de la biblioteca',
          'OK',
          { duration: 4000 },
        );
      },
      error: (err) =>
        this.snack.open(err?.error?.error ?? 'No se pudo eliminar', 'OK', { duration: 5000 }),
    });
  }
}
