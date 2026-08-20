/** Utilidades de fecha en hora local del navegador, semana empezando en lunes. */

/** YYYY-MM-DD local. `toISOString()` NO sirve: convierte a UTC y desplaza el día. */
export function toISODate(date: Date): string {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, '0');
  const d = `${date.getDate()}`.padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Interpreta YYYY-MM-DD como fecha local (new Date('...') lo trataría como UTC). */
export function fromISODate(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function addMonths(date: Date, months: number): Date {
  const next = new Date(date.getFullYear(), date.getMonth() + months, 1);
  // Conserva el día si existe en el mes destino (31 ene + 1 mes -> 28/29 feb).
  const lastDay = new Date(next.getFullYear(), next.getMonth() + 1, 0).getDate();
  next.setDate(Math.min(date.getDate(), lastDay));
  return next;
}

/** Lunes de la semana que contiene `date`. */
export function startOfWeek(date: Date): Date {
  const day = date.getDay(); // 0 = domingo
  const offset = day === 0 ? -6 : 1 - day;
  return addDays(startOfDay(date), offset);
}

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function endOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function weekDays(anchor: Date): Date[] {
  const monday = startOfWeek(anchor);
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

/**
 * Rejilla del mes en semanas completas de lunes a domingo, incluyendo los días
 * de relleno del mes anterior y siguiente para que la cuadrícula no tenga huecos.
 */
export function monthGrid(anchor: Date): Date[][] {
  const first = startOfMonth(anchor);
  const last = endOfMonth(anchor);
  const start = startOfWeek(first);

  const weeks: Date[][] = [];
  let cursor = start;
  while (cursor <= last || weeks.length === 0 || cursor.getDay() !== 1) {
    weeks.push(Array.from({ length: 7 }, (_, i) => addDays(cursor, i)));
    cursor = addDays(cursor, 7);
    if (weeks.length >= 6) break;
  }
  return weeks;
}
