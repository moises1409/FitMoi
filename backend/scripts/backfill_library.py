"""Siembra la biblioteca con los registros que ya existían.

Sin esto, la biblioteca arranca vacía y las comidas anteriores a la funcionalidad
no aparecen como sugerencias. Es idempotente: se puede ejecutar varias veces.

    cd backend && .venv/Scripts/python.exe scripts/backfill_library.py
"""

import os
import sys
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models.food_log import FoodLog  # noqa: E402
from app.services import library_service  # noqa: E402
from app.services.library_service import MACRO_KEYS  # noqa: E402


def run() -> None:
    app = create_app()
    with app.app_context():
        logs = FoodLog.query.order_by(FoodLog.created_at.asc()).all()
        created = reused = 0

        for log in logs:
            name = (log.description or '').strip()
            if not name:
                continue

            existed = library_service.find_by_name(name) is not None
            template = library_service.upsert_template(
                name=name,
                macros={
                    'calories': log.total_calories or 0,
                    'proteins': log.proteins or 0,
                    'carbs': log.carbs or 0,
                    'fats': log.fats or 0,
                    'fiber': log.fiber or 0,
                },
                kind='dish' if log.foods_detected else 'food',
                components=log.foods_detected or [],
                photo_path=log.photo_path,
                source='ai',
            )
            if template is None:
                continue

            created_at = log.created_at
            if created_at is not None and created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            library_service.record_usage(template, log.meal_type or 'snack', created_at)
            reused += existed
            created += not existed

        db.session.commit()
        total = sum(1 for _ in logs)
        print(f'{total} registros procesados -> {created} plantillas nuevas, {reused} reutilizadas')

        for t in library_service.suggest(None, 10)['suggested']:
            print(f"  {t['times_used']:>3}x  {t['calories']:>6.0f} kcal  {t['name'][:60]}")


if __name__ == '__main__':
    run()
