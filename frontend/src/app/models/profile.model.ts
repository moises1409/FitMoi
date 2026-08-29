export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface Challenge {
  what: string;
  when?: string;
}

/** Gasto energético estimado a partir de los datos del perfil. */
export interface EnergyEstimate {
  bmr: number;
  tdee: number;
  activity_factor: number;
  target_lose: number;
  target_gain: number;
}

/** Objetivos diarios calculados a partir del perfil. */
export interface DailyTargets {
  calories: number;
  proteins: number;
  carbs: number;
  fats: number;
  fiber: number;
  saturated_fat_max: number;
  salt_max: number;
  protein_per_kg: number;
  goal_direction: string;
  goal_label: string;
  tdee: number;
  /** De dónde sale cada número, paso a paso. */
  basis: string[];
  notes: string[];
  /** Campos que el usuario ha fijado a mano. */
  overridden: string[];
}

export const GOAL_DIRECTIONS = [
  { value: 'lose', label: 'Perder grasa' },
  { value: 'recomp', label: 'Recomposición' },
  { value: 'maintain', label: 'Mantenerme' },
  { value: 'gain', label: 'Ganar masa' },
];

/** Una pesada del histórico. Los campos de composición solo llegan de Withings. */
export interface WeightEntry {
  id: number;
  weight_kg: number;
  measured_on: string;
  source: 'manual' | 'chat' | 'withings';
  note: string | null;
  // ── Composición corporal (báscula Withings); null en una pesada manual ──
  fat_ratio: number | null;       // % de masa grasa
  fat_mass_kg: number | null;
  muscle_mass_kg: number | null;
  bone_mass_kg: number | null;
  hydration_kg: number | null;
  muscle_ratio: number | null;    // % derivado respecto al peso
  bone_ratio: number | null;
  water_ratio: number | null;
  has_composition: boolean;
}

/** Evolución del peso y si toca volver a pesarse. */
export interface WeightSummary {
  /** En orden cronológico, de la más antigua a la más reciente. */
  entries: WeightEntry[];
  current: number | null;
  /** Última pesada completa: lleva la composición corporal para la ficha. */
  current_entry: WeightEntry | null;
  change_last: number | null;
  change_total: number | null;
  days_since: number | null;
  check_every_days: number;
  due: boolean;
  next_due: string | null;
}

export interface UserProfile {
  id: number;
  age: number | null;
  sex: 'male' | 'female' | 'other' | null;
  weight_kg: number | null;
  height_cm: number | null;
  training_days_per_week: number | null;
  activity_level: string | null;
  job_activity: string | null;
  job: string | null;
  location: string | null;
  primary_goal: string | null;
  free_notes: string | null;

  sports: string[];
  goals: string[];
  conditions: string[];
  injuries_current: string[];
  injuries_past: string[];
  diet_notes: string[];
  challenges: Challenge[];

  conversation: ChatMessage[];
  completed: boolean;
  completeness: number;
  missing: string[];
  energy: EnergyEstimate | null;
  targets: DailyTargets | null;
  weight: WeightSummary;
  weight_check_every_days: number | null;
  goal_direction: string | null;
  target_overrides: Record<string, number>;
  updated_at: string | null;
}

export interface ChatResponse {
  reply: string;
  /** Campos que el entrenador ha anotado en este turno. */
  changed: string[];
  profile: UserProfile;
}

export const SEX_LABELS: Record<string, string> = {
  male: 'Hombre',
  female: 'Mujer',
  other: 'Otro',
};

export const ACTIVITY_LABELS: Record<string, string> = {
  sedentary: 'Sedentario',
  light: 'Ligero',
  moderate: 'Moderado',
  active: 'Activo',
  very_active: 'Muy activo',
};

export const JOB_ACTIVITY_LABELS: Record<string, string> = {
  sedentary: 'De oficina',
  standing: 'De pie',
  physical: 'Físico',
};

/** Nombres legibles de los campos, para avisar de qué acaba de anotar. */
export const FIELD_LABELS: Record<string, string> = {
  age: 'edad',
  sex: 'sexo',
  weight_kg: 'peso',
  height_cm: 'altura',
  training_days_per_week: 'días de entreno',
  activity_level: 'nivel de actividad',
  job_activity: 'tipo de trabajo',
  job: 'trabajo',
  location: 'dónde vives',
  primary_goal: 'objetivo principal',
  free_notes: 'notas',
  sports: 'deportes',
  goals: 'objetivos',
  conditions: 'condiciones médicas',
  injuries_current: 'lesiones actuales',
  injuries_past: 'lesiones pasadas',
  diet_notes: 'alimentación',
  challenges: 'retos',
};
