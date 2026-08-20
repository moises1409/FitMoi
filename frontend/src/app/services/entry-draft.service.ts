import { Injectable, signal } from '@angular/core';
import {
  AnalysisDetail,
  Confidence,
  FoodAnalysis,
  FoodItem,
  FoodTemplate,
  MACRO_KEYS,
  MacroKey,
  Totals,
  detectMealType,
} from '../models/food.model';

const STORAGE_KEY = 'fitmoi-draft';

/**
 * El alimento que se está a punto de guardar. Un solo elemento, no una lista:
 * cada comida se registra por separado y se vuelve al día correspondiente.
 *
 * Los macros son SIEMPRE por 1 porción; el escalado lo aplican la vista y el
 * backend. Se persiste en sessionStorage para que salir a la cámara o recargar
 * no pierda lo que llevabas.
 */
export interface EntryDraft {
  template_id?: number;
  name: string;
  quantity: string;
  portion: number;
  calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  saturated_fat: number;
  salt: number;
  components: FoodItem[];
  /** Estimación de porciones y valoración del LLM. */
  analysis?: AnalysisDetail;
  confidence?: Confidence;
  origin: 'library' | 'photo' | 'text';
  photo_filename?: string | null;
  photo_url?: string | null;
  /** Momento de la ingesta en ISO local (YYYY-MM-DDTHH:mm), editable. */
  logged_at: string;
  meal_type: string;
  notes: string;
}

/** ISO local sin zona: lo que esperan <input type="date"> y <input type="time">. */
function localISO(date: Date): string {
  const p = (n: number) => `${n}`.padStart(2, '0');
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}` +
    `T${p(date.getHours())}:${p(date.getMinutes())}`;
}

/**
 * Momento por defecto.
 *
 * `preferredTime` ('HH:MM') es la hora a la que se registró este alimento la
 * última vez: si siempre desayunas lo mismo a las 8:30, proponer la hora actual
 * obligaría a corregirla cada vez.
 */
function defaultMoment(targetDate?: string | null, preferredTime?: string | null): string {
  const now = new Date();
  const base = new Date(now);

  if (targetDate) {
    const [y, m, d] = targetDate.split('-').map(Number);
    if (y && m && d) base.setFullYear(y, m - 1, d);
  }

  const [hh, mm] = (preferredTime ?? '').split(':').map(Number);
  if (Number.isInteger(hh) && Number.isInteger(mm)) {
    base.setHours(hh, mm, 0, 0);
  } else if (targetDate && base.toDateString() !== now.toDateString()) {
    // Día pasado sin hora conocida: mediodía es menos raro que las 00:00.
    base.setHours(13, 0, 0, 0);
  }

  return localISO(base);
}

@Injectable({ providedIn: 'root' })
export class EntryDraftService {
  readonly draft = signal<EntryDraft | null>(null);

  constructor() {
    this.restore();
  }

  fromTemplate(template: FoodTemplate, targetDate?: string | null): EntryDraft {
    return this.set({
      template_id: template.id,
      name: template.name,
      quantity: template.quantity_label,
      portion: 1,
      calories: template.calories,
      proteins: template.proteins,
      carbs: template.carbs,
      fats: template.fats,
      fiber: template.fiber,
      saturated_fat: template.saturated_fat ?? 0,
      salt: template.salt ?? 0,
      components: template.components ?? [],
      analysis: template.analysis,
      origin: 'library',
      photo_url: template.photo_url,
      // Repite la hora y la franja de la última vez que lo tomaste.
      logged_at: defaultMoment(targetDate, template.usual_time),
      meal_type: template.usual_meal_type ?? detectMealType(),
      notes: '',
    });
  }

  fromAnalysis(analysis: FoodAnalysis, targetDate?: string | null): EntryDraft {
    return this.set({
      name: analysis.description,
      quantity: '',
      portion: 1,
      calories: analysis.total_calories,
      proteins: analysis.proteins,
      carbs: analysis.carbs,
      fats: analysis.fats,
      fiber: analysis.fiber,
      saturated_fat: analysis.saturated_fat ?? 0,
      salt: analysis.salt ?? 0,
      components: analysis.foods_detected ?? [],
      analysis: {
        is_shared_dish: analysis.is_shared_dish,
        servings_in_photo: analysis.servings_in_photo,
        portion_summary: analysis.portion_summary,
        calories_min: analysis.calories_min,
        calories_max: analysis.calories_max,
        assessment: analysis.assessment,
      },
      confidence: analysis.confidence,
      origin: analysis.source === 'text' ? 'text' : 'photo',
      photo_filename: analysis.photo_filename ?? null,
      logged_at: defaultMoment(targetDate),
      meal_type: detectMealType(),
      notes: '',
    });
  }

  patch(changes: Partial<EntryDraft>): void {
    const current = this.draft();
    if (!current) return;
    this.set({ ...current, ...changes });
  }

  /** Macros escalados a la porción, para mostrar y editar. */
  scaled(key: MacroKey): number {
    const d = this.draft();
    if (!d) return 0;
    return Math.round((d[key] || 0) * d.portion * 10) / 10;
  }

  totals(): Totals {
    const d = this.draft();
    const out = { calories: 0, proteins: 0, carbs: 0, fats: 0, fiber: 0, saturated_fat: 0, salt: 0 } as Totals;
    if (!d) return out;
    for (const key of MACRO_KEYS) {
      out[key] = Math.round((d[key] || 0) * d.portion * 10) / 10;
    }
    return out;
  }

  clear(): void {
    this.draft.set(null);
    sessionStorage.removeItem(STORAGE_KEY);
  }

  /** Payload de POST /api/food/log: un único elemento. */
  toPayload(): Record<string, unknown> | null {
    const d = this.draft();
    if (!d) return null;
    return {
      meal_type: d.meal_type,
      notes: d.notes,
      logged_at: d.logged_at,
      photo_filename: d.photo_filename ?? null,
      confidence: d.confidence ?? 'high',
      items: [{
        template_id: d.template_id,
        name: d.name,
        quantity: d.quantity,
        portion: d.portion,
        components: d.components,
        analysis: d.analysis,
        photo_filename: d.photo_filename ?? null,
        source: 'ai',
        calories: d.calories,
        proteins: d.proteins,
        carbs: d.carbs,
        fats: d.fats,
        fiber: d.fiber,
        saturated_fat: d.saturated_fat,
        salt: d.salt,
      }],
      analysis: d.analysis ?? null,
    };
  }

  private set(draft: EntryDraft): EntryDraft {
    this.draft.set(draft);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // Cuota llena o modo privado: sigue vivo en memoria.
    }
    return draft;
  }

  private restore(): void {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (raw) this.draft.set(JSON.parse(raw) as EntryDraft);
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }
}
