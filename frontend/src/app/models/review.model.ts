import { DailyTargets } from './profile.model';

/** Totales de un día de la semana (solo días con comidas). */
export interface ReviewDay {
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

/** Adherencia a los objetivos diarios, sobre los días registrados. */
export interface NutritionAdherence {
  calories_target: number;
  protein_target: number;
  avg_calories_vs_target_pct: number | null;
  days_within_target: number;
  days_over_target: number;
  days_meeting_protein: number;
}

export interface NutritionMetrics {
  days_logged: number;
  total_calories: number;
  avg_calories: number;
  avg_proteins: number;
  avg_carbs: number;
  avg_fats: number;
  avg_fiber: number;
  avg_saturated_fat: number;
  avg_salt: number;
  days: ReviewDay[];
  adherence?: NutritionAdherence;
}

export interface ActivityFamilyBreakdown {
  family: string;
  label: string;
  color: string;
  sessions: number;
  minutes: number;
}

export interface ActivityMetrics {
  sessions: number;
  minutes: number;
  days_active: number;
  training_days_target: number | null;
  calories: number;
  by_family: ActivityFamilyBreakdown[];
}

export interface EnergyMetrics {
  days_recorded: number;
  avg_burned: number | null;
}

export interface WeightMetrics {
  entries: number;
  start: number | null;
  end: number | null;
  delta: number | null;
}

export interface WeeklyMetrics {
  week_start: string;
  week_end: string;
  nutrition: NutritionMetrics;
  activity: ActivityMetrics;
  energy: EnergyMetrics;
  weight: WeightMetrics;
  targets: DailyTargets | null;
  has_data: boolean;
}

export type Tendencia = 'mejor' | 'igual' | 'peor' | 'sin_datos';

export interface ReviewComparison {
  tendencia: Tendencia;
  detalle: string;
  factores: string[];
}

/** Lo que redacta el LLM sobre las cifras de la semana. */
export interface ReviewNarrative {
  resumen: string;
  lo_bueno: string[];
  a_mejorar: string[];
  comparativa: ReviewComparison;
  recomendaciones: string[];
}

export interface WeekRef {
  iso_year: number;
  iso_week: number;
  week_start: string;
  week_end: string;
}

export interface WeeklyReviewResponse {
  week: WeekRef;
  is_current: boolean;
  is_closed: boolean;
  can_generate: boolean;
  generated: boolean;
  metrics: WeeklyMetrics;
  previous: WeeklyMetrics | null;
  narrative: ReviewNarrative | null;
  model: string | null;
  generated_at: string | null;
}

/** Tarjeta de la lista de semanas guardadas. */
export interface WeeklyReviewListItem {
  week_start: string;
  week_end: string;
  iso_year: number;
  iso_week: number;
  resumen: string;
  tendencia: Tendencia;
  avg_calories: number;
  days_logged: number;
  sessions: number;
}

export const TENDENCIA_LABELS: Record<Tendencia, string> = {
  mejor: 'Mejor que la semana anterior',
  igual: 'Similar a la semana anterior',
  peor: 'Peor que la semana anterior',
  sin_datos: 'Sin comparativa',
};

export const TENDENCIA_ICONS: Record<Tendencia, string> = {
  mejor: 'trending_up',
  igual: 'trending_flat',
  peor: 'trending_down',
  sin_datos: 'remove',
};
