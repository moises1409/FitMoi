/** Un alimento del desglose, con el peso estimado del que salen sus nutrientes. */
export interface FoodItem {
  name: string;
  quantity: string;
  calories: number;
  grams?: number;
  proteins?: number;
  carbs?: number;
  fats?: number;
  saturated_fat?: number;
  fiber?: number;
  salt?: number;
}

export type Confidence = 'high' | 'medium' | 'low';

/** Valoración cualitativa: qué domina el plato y qué se puede mejorar. */
export interface Assessment {
  summary: string;
  positives: string[];
  concerns: string[];
  tip: string;
}

/** Estimación de porciones y valoración, que se conservan con el alimento. */
export interface AnalysisDetail {
  is_shared_dish?: boolean;
  servings_in_photo?: number;
  portion_summary?: string;
  calories_min?: number;
  calories_max?: number;
  assessment?: Assessment;
}

/** Resultado devuelto por el LLM (fotos y/o descripción). */
export interface FoodAnalysis {
  description: string;
  is_shared_dish: boolean;
  servings_in_photo: number;
  portion_summary: string;
  foods_detected: FoodItem[];
  total_calories: number;
  calories_min: number;
  calories_max: number;
  proteins: number;
  carbs: number;
  fats: number;
  saturated_fat: number;
  fiber: number;
  salt: number;
  confidence: Confidence;
  assessment: Assessment;
  source?: 'photo' | 'text';
  photo_filename?: string | null;
  photo_filenames?: string[];
}

/** Entrada reutilizable de la biblioteca. Macros para 1 porción. */
export interface FoodTemplate {
  id: number;
  kind: 'dish' | 'food';
  name: string;
  quantity_label: string;
  calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  components: FoodItem[];
  saturated_fat: number;
  salt: number;
  analysis: AnalysisDetail;
  photo_url: string | null;
  source: 'ai' | 'manual';
  times_used: number;
  last_used_at: string | null;
  /** Hora ('HH:MM') y franja de la última vez que se registró: valores por
   *  defecto al volver a añadirlo. */
  usual_time: string | null;
  usual_meal_type: string | null;
}

export interface LibrarySuggestions {
  suggested: FoodTemplate[];
  recent: FoodTemplate[];
  total: number;
}

/** Elemento tal como queda guardado dentro de un registro, ya escalado. */
export interface LoggedItem {
  template_id: number | null;
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
  analysis?: AnalysisDetail;
}

export type MacroKey =
  | 'calories' | 'proteins' | 'carbs' | 'fats' | 'fiber' | 'saturated_fat' | 'salt';

export const MACRO_KEYS: MacroKey[] = [
  'calories', 'proteins', 'carbs', 'fats', 'fiber', 'saturated_fat', 'salt',
];

/** Los que se muestran como pastillas y se editan a mano. */
export const MACRO_FIELDS: { key: MacroKey; label: string; short: string; cls: string }[] = [
  { key: 'proteins', label: 'Proteínas', short: 'P', cls: 'protein' },
  { key: 'carbs', label: 'Carbos', short: 'C', cls: 'carbs' },
  { key: 'fats', label: 'Grasas', short: 'G', cls: 'fat' },
  { key: 'saturated_fat', label: 'Saturadas', short: 'Sat', cls: 'sat' },
  { key: 'fiber', label: 'Fibra', short: 'F', cls: 'fiber' },
  { key: 'salt', label: 'Sal', short: 'Sal', cls: 'salt' },
];

export interface Totals {
  calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  saturated_fat: number;
  salt: number;
}

export interface DailyTotals extends Totals {}

export interface FoodLog {
  id: number;
  meal_type: string;
  photo_url: string | null;
  description: string;
  foods_detected: FoodItem[];
  items: LoggedItem[];
  total_calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  saturated_fat: number;
  salt: number;
  analysis: AnalysisDetail;
  confidence: Confidence;
  notes: string;
  created_at: string;
}

/** Objetivo por defecto mientras el perfil no dé para calcular el real. */
export const FALLBACK_GOAL = 2000;

export interface DayResponse {
  date: string;
  is_today: boolean;
  items: FoodLog[];
  totals: DailyTotals;
  /** Objetivos del perfil; null si aún no hay datos suficientes. */
  targets: import('./profile.model').DailyTargets | null;
  activities: import('./activity.model').Activity[];
  activity_totals: import('./activity.model').ActivityTotals;
}

export type TodayResponse = DayResponse;

/** Totales agregados de un día natural, sin traer los registros. */
export interface DaySummary {
  date: string;
  meals: number;
  calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  saturated_fat: number;
  salt: number;
}

export interface SummaryStats {
  days_logged: number;
  days_in_range: number;
  total_calories: number;
  avg_calories: number;
  best_day: string | null;
}

export interface SummaryResponse {
  targets: import('./profile.model').DailyTargets | null;
  activity_families: import('./activity.model').ActivityFamily[];
  /** Familias con actividad por día (YYYY-MM-DD), para los puntos del mes. */
  activities_by_day: Record<string, import('./activity.model').DayActivityMark[]>;
  from: string;
  to: string;
  today: string;
  days: DaySummary[];
  stats: SummaryStats;
}

export interface LogsPage {
  items: FoodLog[];
  total: number;
  pages: number;
  page: number;
}

export const MEAL_TYPES = [
  { value: 'breakfast', label: 'Desayuno', icon: 'free_breakfast' },
  { value: 'lunch', label: 'Comida', icon: 'restaurant' },
  { value: 'snack', label: 'Merienda', icon: 'apple' },
  { value: 'dinner', label: 'Cena', icon: 'dinner_dining' },
];

/** Franja probable según la hora: sesga las sugerencias y preselecciona el tipo. */
export function detectMealType(date = new Date()): string {
  const hour = date.getHours();
  if (hour >= 6 && hour < 11) return 'breakfast';
  if (hour >= 13 && hour < 16) return 'lunch';
  if (hour >= 19 && hour < 23) return 'dinner';
  return 'snack';
}

export const PORTION_PRESETS = [0.5, 1, 1.5, 2];
