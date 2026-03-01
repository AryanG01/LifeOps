# apps/api/src/api/routes/replay.py
from fastapi import APIRouter
from core.llm.extractor import extract_all_pending

router = APIRouter()


@router.post("/extract")
def replay_extract(prompt_version: str = "v2"):
    """Re-run extraction for all messages with a new prompt version."""
    success, failed = extract_all_pending(prompt_version)
    return {"prompt_version": prompt_version, "extracted": success, "failed": failed}
