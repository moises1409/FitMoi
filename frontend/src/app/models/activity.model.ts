/** Familia de actividad con su color fijo. Cinco como máximo: por encima de
 *  siete u ocho tonos dejan de distinguirse, sobre todo con daltonismo. */
export interface ActivityFamily {
  key: string;
  label: string;
  color: string;
  icon: string;
}

export interface Activity {
  id: number;
  /** 'manual' o 'whoop': la ficha es la misma, cambia lo que trae relleno. */
  source: 'manual' | 'whoop';
  external_id: string | null;
  activity_type: string;
  sport_name: string;
  started_at: string;
  duration_min: number | null;
  calories: number | null;
  /** Cómo fue la sesión, del 1 al 5. */
  feeling: number | null;
  notes: string | null;
  /** Strain, pulso, distancia y zonas: solo cuando hay pulsera. */
  metrics: Record<string, unknown>;
}

export interface ActivityTotals {
  sessions: number;
  minutes: number;
  /** Informativo: NO se resta del objetivo, que ya incluye factor de actividad. */
  calories: number;
}

/** Familias con actividad en un día, para los puntos del calendario. */
export interface DayActivityMark {
  family: string;
  count: number;
}

export const FEELING_LABELS: Record<number, string> = {
  1: 'Muy mal',
  2: 'Floja',
  3: 'Normal',
  4: 'Bien',
  5: 'Genial',
};

/** Sugerencias del formulario, en el orden en que se usan. */
export const SPORT_SUGGESTIONS = [
  'Circuit training',
  'Calistenia',
  'Pádel',
  'Fuerza en gimnasio',
  'Correr',
  'Bici',
  'Yoga',
  'Caminar',
];
