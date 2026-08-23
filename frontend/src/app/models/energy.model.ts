/** Gasto energético de un día: las calorías gastadas en total.
 *
 *  Es un valor único por día (a diferencia de las calorías de cada actividad,
 *  que son por sesión). Hoy se introduce a mano; en el futuro lo rellenará
 *  Whoop, de ahí el `source`. */
export interface EnergyEntry {
  id: number;
  calories: number;
  measured_on: string;
  /** 'manual' o 'whoop': de dónde salió el dato. */
  source: 'manual' | 'whoop';
  note: string | null;
}

export interface EnergyDayResponse {
  entry: EnergyEntry | null;
}
