# apps/api/src/api/routes/sync.py
from fastapi import APIRouter
from core.config import get_settings
from core.pipeline.normalizer import normalize_all_pending
from core.llm.extractor import extract_all_pending

router = APIRouter()


@router.post("/run")
def run_sync():
    settings = get_settings()
    normalized = normalize_all_pending()
    success, failed = extract_all_pending(settings.llm_prompt_version)
    return {"normalized": normalized, "extracted": success, "extraction_failed": failed}
