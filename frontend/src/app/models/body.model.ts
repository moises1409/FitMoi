/** Una toma de medidas corporales (cinta), fechada. Contornos en cm. */
export interface BodyMeasurement {
  id: number;
  measured_on: string;
  waist_cm: number | null;
  abdomen_cm: number | null;
  chest_cm: number | null;
  biceps_left_cm: number | null;
  biceps_right_cm: number | null;
  note: string | null;
}

/** Valor actual y variación de un contorno a lo largo del histórico. */
export interface MeasurementChange {
  label: string;
  current: number;
  change_last: number | null;
  change_total: number | null;
}

export interface MeasurementsSummary {
  /** Cronológico: de la toma más antigua a la más reciente. */
  entries: BodyMeasurement[];
  latest: BodyMeasurement | null;
  /** Cambios por campo (waist_cm, abdomen_cm, chest_cm, biceps_cm). */
  changes: Record<string, MeasurementChange>;
}

/** Una foto de progreso, fechada. */
export interface BodyPhoto {
  id: number;
  taken_on: string;
  pose: string | null;
  filename: string;
  note: string | null;
  /** Ruta relativa servida por el backend (bajo el candado, vía cookie). */
  url: string;
}

export interface BodySummary {
  measurements: MeasurementsSummary;
  photos: BodyPhoto[];
}

/** Claves de los contornos numéricos (las que el formulario y las gráficas usan). */
export type MeasurementKey =
  | 'waist_cm' | 'abdomen_cm' | 'chest_cm' | 'biceps_left_cm' | 'biceps_right_cm';

/** Campos numéricos de una toma, con su etiqueta, para formulario y vista. */
export const MEASUREMENT_FIELDS: { key: MeasurementKey; label: string }[] = [
  { key: 'waist_cm', label: 'Cintura' },
  { key: 'abdomen_cm', label: 'Abdomen' },
  { key: 'chest_cm', label: 'Pectoral' },
  { key: 'biceps_left_cm', label: 'Bíceps izq.' },
  { key: 'biceps_right_cm', label: 'Bíceps der.' },
];
