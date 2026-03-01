# apps/api/src/api/routes/digest.py
from fastapi import APIRouter
from core.db.engine import get_db
from core.db.models import Digest
from core.digest.generator import generate_digest
from datetime import date

router = APIRouter()


@router.get("/today")
def get_digest_today(user_id: str = "00000000-0000-0000-0000-000000000001"):
    content = generate_digest(user_id)
    return {"date": str(date.today()), "content_md": content}


@router.get("/{for_date}")
def get_digest(for_date: str, user_id: str = "00000000-0000-0000-0000-000000000001"):
    with get_db() as db:
        d = db.query(Digest).filter_by(user_id=user_id, date=for_date).first()
        if not d:
            return {"date": for_date, "content_md": None}
        return {"date": str(d.date), "content_md": d.content_md, "regime": d.regime}
