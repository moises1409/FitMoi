"""Calorías gastadas por día: registro, consulta y agregado para el calendario.

El gasto del día es un valor único por día natural (a diferencia de las
calorías de cada `Activity`, que son por sesión e informativas). Hoy se
introduce a mano; en el futuro lo rellenará Whoop. Por eso hay una entrada por
día como mucho y `record` hace upsert: reintroducir el mismo día corrige la
fila, que es lo que se espera al reescribir un dato.
"""

from datetime import date

from sqlalchemy import func

from .. import db
from ..models.energy_expenditure import EnergyExpenditure

MIN_CALORIES, MAX_CALORIES = 0.0, 20000.0


def for_day(day: date) -> EnergyExpenditure | None:
    return EnergyExpenditure.query.filter_by(measured_on=day).first()


def record(calories, day: date, source: str = 'manual',
           note: str | None = None) -> EnergyExpenditure:
    """Registra el gasto de un día. Uno por día: repetir corrige el anterior."""
    try:
        value = round(float(calories), 1)
    except (TypeError, ValueError):
        raise ValueError('Las calorías deben ser numéricas.')
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError('Las calorías no son un número válido.')
    if not (MIN_CALORIES <= value <= MAX_CALORIES):
        raise ValueError(f'Las calorías deben estar entre {MIN_CALORIES:.0f} y {MAX_CALORIES:.0f}.')

    if day > date.today():
        raise ValueError('No puedes registrar el gasto de un día futuro.')

    entry = EnergyExpenditure.query.filter_by(measured_on=day).first()
    if entry:
        entry.calories = value
        entry.source = source
        if note is not None:
            entry.note = note
    else:
        entry = EnergyExpenditure(
            calories=value, measured_on=day, source=source, note=note,
        )
        db.session.add(entry)

    db.session.flush()
    return entry


def delete(entry_id: int) -> bool:
    entry = db.session.get(EnergyExpenditure, entry_id)
    if not entry:
        return False
    db.session.delete(entry)
    db.session.flush()
    return True


def by_day(start_day: date, end_day: date, tz_name: str) -> dict:
    """Calorías gastadas por día natural del rango, para pintar el mes.

    `measured_on` ya es una fecha natural (sin hora), así que a diferencia de
    comidas o actividades no hace falta convertir zonas: se filtra por rango de
    fechas directamente. `tz_name` se acepta por simetría con los otros
    agregados por si algún día el gasto pasa a guardarse con marca de tiempo.
    """
    filas = (
        EnergyExpenditure.query
        .filter(EnergyExpenditure.measured_on >= start_day,
                EnergyExpenditure.measured_on <= end_day)
        .all()
    )
    return {e.measured_on.isoformat(): round(e.calories, 1) for e in filas}
