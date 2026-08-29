"""Histórico de peso.

El peso deja de ser un valor que se pisa: cada pesada queda registrada para
poder ver la evolución. `user_profiles.weight_kg` se mantiene como el peso
actual (lo usan los cálculos de objetivos) y siempre refleja la última entrada.
"""

from datetime import date, timedelta

from .. import db
from ..models.user_profile import UserProfile
from ..models.weight_entry import WeightEntry

DEFAULT_CHECK_DAYS = 30
MIN_KG, MAX_KG = 20.0, 400.0

# Campos de composición corporal que puede traer la báscula (todos opcionales).
COMPOSITION_FIELDS = (
    'fat_ratio', 'fat_mass_kg', 'muscle_mass_kg', 'bone_mass_kg', 'hydration_kg',
)


def history(limit: int = 60) -> list:
    """Pesadas de la más reciente a la más antigua."""
    return (
        WeightEntry.query.order_by(WeightEntry.measured_on.desc())
        .limit(limit)
        .all()
    )


def latest() -> WeightEntry | None:
    return WeightEntry.query.order_by(WeightEntry.measured_on.desc()).first()


def record(profile: UserProfile, weight_kg, when: date | None = None,
           source: str = 'manual', note: str | None = None,
           composition: dict | None = None) -> WeightEntry:
    """Registra una pesada. Una por día: repetir el mismo día corrige la anterior.

    `composition` (opcional) trae la composición corporal de una báscula
    inteligente (grasa, músculo, hueso, agua). Solo se aplican las claves de
    `COMPOSITION_FIELDS` que vengan con valor; las ausentes se conservan.
    """
    try:
        value = round(float(weight_kg), 1)
    except (TypeError, ValueError):
        raise ValueError('El peso debe ser numérico.')
    if not (MIN_KG <= value <= MAX_KG):
        raise ValueError(f'El peso debe estar entre {MIN_KG:.0f} y {MAX_KG:.0f} kg.')

    day = when or date.today()
    if day > date.today():
        raise ValueError('No puedes registrar una pesada futura.')

    entry = WeightEntry.query.filter_by(measured_on=day).first()
    if entry:
        entry.weight_kg = value
        entry.source = source
        if note is not None:
            entry.note = note
    else:
        entry = WeightEntry(weight_kg=value, measured_on=day, source=source, note=note)
        db.session.add(entry)

    _apply_composition(entry, composition)

    db.session.flush()
    _sync_current(profile)
    return entry


def record_withings(profile: UserProfile, weight_kg, when: date,
                    composition: dict | None = None) -> str:
    """Registra una pesada traída de la báscula Withings.

    Respeta una corrección manual: si el día ya tiene una pesada con
    `source='manual'`, no la pisa (devuelve 'skipped'), igual que hace el sync
    de gasto de Whoop con `energy_service.record_whoop`. Si no, crea o actualiza
    la fila con el peso y la composición de la báscula (`source='withings'`).

    Devuelve 'created', 'updated' o 'skipped'. NO hace commit (lo hace quien llama).
    """
    entry = WeightEntry.query.filter_by(measured_on=when).first()
    if entry is not None and entry.source == 'manual':
        return 'skipped'

    is_new = entry is None
    record(profile, weight_kg, when=when, source='withings', composition=composition)
    return 'created' if is_new else 'updated'


def _apply_composition(entry: WeightEntry, composition: dict | None) -> None:
    """Copia a la fila las claves de composición que vengan con valor numérico."""
    if not composition:
        return
    for field in COMPOSITION_FIELDS:
        value = composition.get(field)
        if value is None:
            continue
        try:
            setattr(entry, field, round(float(value), 2))
        except (TypeError, ValueError):
            continue


def delete(entry_id: int, profile: UserProfile) -> bool:
    entry = db.session.get(WeightEntry, entry_id)
    if not entry:
        return False
    db.session.delete(entry)
    db.session.flush()
    _sync_current(profile)
    return True


def _sync_current(profile: UserProfile) -> None:
    """El peso del perfil es siempre el de la última pesada."""
    ultima = latest()
    profile.weight_kg = ultima.weight_kg if ultima else None


def summary(profile: UserProfile) -> dict:
    """Estado del seguimiento: última pesada, variación y si toca pesarse."""
    entries = history()
    cada = profile.weight_check_every_days or DEFAULT_CHECK_DAYS

    if not entries:
        return {
            'entries': [],
            'current': None,
            'current_entry': None,
            'change_last': None,
            'change_total': None,
            'days_since': None,
            'check_every_days': cada,
            'due': True,
            'next_due': date.today().isoformat(),
        }

    actual, dias = entries[0], (date.today() - entries[0].measured_on).days
    anterior = entries[1] if len(entries) > 1 else None
    primera = entries[-1]

    return {
        # En orden cronológico: es como se lee una evolución.
        'entries': [e.to_dict() for e in reversed(entries)],
        'current': actual.weight_kg,
        # Última pesada completa: lleva la composición corporal para la ficha.
        'current_entry': actual.to_dict(),
        'change_last': round(actual.weight_kg - anterior.weight_kg, 1) if anterior else None,
        'change_total': round(actual.weight_kg - primera.weight_kg, 1) if primera is not actual else None,
        'days_since': dias,
        'check_every_days': cada,
        'due': dias >= cada,
        'next_due': (actual.measured_on + timedelta(days=cada)).isoformat(),
    }
