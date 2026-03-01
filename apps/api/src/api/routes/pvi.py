# apps/api/src/api/routes/pvi.py
from fastapi import APIRouter
from core.pvi.engine import compute_pvi_daily
from core.db.engine import get_db
from core.db.models import PVIDailyScore
from datetime import date

router = APIRouter()


@router.get("/today")
def get_pvi_today(user_id: str = "00000000-0000-0000-0000-000000000001"):
    result = compute_pvi_daily(user_id)
    return result


@router.get("/{for_date}")
def get_pvi(for_date: str, user_id: str = "00000000-0000-0000-0000-000000000001"):
    with get_db() as db:
        row = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()
        if not row:
            return {"date": for_date, "score": None, "regime": None}
        return {"date": str(row.date), "score": row.score, "regime": row.regime,
                "explanation": row.explanation}
