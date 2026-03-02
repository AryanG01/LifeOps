"""
LLM extraction pipeline.
Calls Anthropic API, validates with Pydantic ExtractionResult (extra=forbid),
retries once on invalid JSON, records LLMRun audit row per attempt.
"""
import json
import time
from datetime import datetime, timezone

import structlog

from core.config import get_settings
from core.db.engine import get_db
from core.db.models import (
    ActionItem,
    LLMRun,
    Message,
    MessageLabel,
    MessageSummary,
    ReplyDraft,
    Source,
)
from core.llm.prompts.v1 import SYSTEM_PROMPT, USER_TEMPLATE
from core.schemas.llm import ExtractionResult

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_llm(system: str, user: str) -> tuple[str, int, int]:
    """
    Call configured LLM provider. Returns (raw_text, input_tokens, output_tokens).
    Supports: "gemini" (via OpenAI-compatible endpoint, free tier) or "anthropic".
    """
    settings = get_settings()

    if settings.llm_provider == "anthropic":
        return _call_anthropic(system, user, settings)
    else:
        return _call_gemini(system, user, settings)


def _call_gemini(system: str, user: str, settings=None, model: str | None = None) -> tuple[str, int, int]:
    """
    Call Gemini via its OpenAI-compatible endpoint.
    Free tier: 250 req/day, 10 RPM for gemini-2.0-flash.
    """
    from openai import OpenAI

    if settings is None:
        settings = get_settings()
    client = OpenAI(
        api_key=settings.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    response = client.chat.completions.create(
        model=model or settings.gemini_model,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = response.choices[0].message.content
    usage = response.usage
    return text, usage.prompt_tokens, usage.completion_tokens


def _call_anthropic(system: str, user: str, settings=None, model: str | None = None) -> tuple[str, int, int]:
    """Call Anthropic Claude API."""
    import anthropic

    if settings is None:
        settings = get_settings()
    resolved_model = model or settings.anthropic_model or "claude-sonnet-4-6"
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=resolved_model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = response.content[0].text
    usage = response.usage
    return text, usage.input_tokens, usage.output_tokens


def _call_llm_raw(system: str, user: str, model_override: str | None = None) -> str:
    """Call LLM with optional model override, return raw text response."""
    settings = get_settings()
    provider = settings.llm_provider
    model = model_override or (
        settings.gemini_model if provider == "gemini" else settings.anthropic_model
    )
    if provider == "gemini":
        raw, _, _ = _call_gemini(system, user, model=model)
    else:
        raw, _, _ = _call_anthropic(system, user, model=model)
    return raw


# ---------------------------------------------------------------------------
# Triage helpers
# ---------------------------------------------------------------------------

_TRIAGE_SYSTEM = (
    'You are a triage filter. Respond with JSON only: {"actionable": true/false}. '
    "An email is actionable if it requires the user to DO something: reply, submit, pay, attend, review, or decide. "
    "Receipts, newsletters, automated notifications with no action required = false."
)

_TRIAGE_USER = "From: {sender}\nSubject: {subject}\nPreview: {preview}"


def _is_actionable(sender: str, subject: str, preview: str) -> bool:
    """Stage 1 triage: cheap LLM call to decide if email warrants full extraction."""
    settings = get_settings()
    user_prompt = _TRIAGE_USER.format(sender=sender, subject=subject, preview=preview[:200])
    try:
        raw = _call_llm_raw(
            _TRIAGE_SYSTEM,
            user_prompt,
            model_override=settings.llm_triage_model,
        )
        return json.loads(raw).get("actionable", True)
    except Exception:
        return True  # fail open


def _record_triage_skip(db, message_id: str, prompt_version: str) -> None:
    db.add(MessageSummary(
        message_id=message_id,
        prompt_version=prompt_version,
        summary_short="triage:skip",
        urgency=0.0,
        extraction_failed=False,
    ))
    db.commit()


def _validate(raw_json: str) -> ExtractionResult:
    """Parse and validate against strict schema. Raises on any error."""
    data = json.loads(raw_json)
    return ExtractionResult.model_validate(data)


def _passes_label_filter(msg_payload_labels: list[str]) -> bool:
    """Check if message's Gmail labels pass the configured filter."""
    settings = get_settings()
    return all(lbl in msg_payload_labels for lbl in settings.llm_label_filter)


def _active_model_name() -> str:
    s = get_settings()
    return s.gemini_model if s.llm_provider == "gemini" else (s.anthropic_model or "claude-sonnet-4-6")


def _record_run(
    db,
    message_id: str,
    prompt_version: str,
    attempt: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    validation_passed: bool,
    validation_error: str | None,
) -> None:
    db.add(LLMRun(
        message_id=message_id,
        prompt_version=prompt_version,
        model=_active_model_name(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        validation_passed=validation_passed,
        validation_error=validation_error,
        attempt=attempt,
    ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_message(message_id: str, prompt_version: str = "v1") -> bool:
    """
    Run LLM extraction on one message.
    Skips if already extracted at this prompt_version.
    Retries once on validation failure.
    Records a LLMRun row per attempt.
    Returns True on success (or skip), False on permanent failure.
    """
    settings = get_settings()

    if settings.llm_mode == "disabled":
        log.info("llm_disabled_skipping", message_id=message_id)
        return True

    with get_db() as db:
        msg = db.query(Message).filter_by(id=message_id).first()
        if not msg:
            log.error("message_not_found", message_id=message_id)
            return False

        existing = db.query(MessageSummary).filter_by(
            message_id=message_id, prompt_version=prompt_version
        ).first()
        if existing:
            log.debug("extraction_already_exists", message_id=message_id, prompt_version=prompt_version)
            return True

        source = db.query(Source).filter_by(id=str(msg.source_id)).first()
        source_type = source.source_type if source else "unknown"

        # Label filter — check raw payload labels
        # (stored in extra_json or we fall back to canvas override)
        msg_label_ids: list[str] = []
        if msg.extra_json and "label_ids" in msg.extra_json:
            msg_label_ids = msg.extra_json["label_ids"]

        passes_filter = (
            (msg.is_canvas and settings.llm_filter_canvas_always)
            or _passes_label_filter(msg_label_ids)
        )
        if not passes_filter:
            log.info("extraction_skipped_label_filter", message_id=message_id)
            return True

        body = msg.body_full or msg.body_preview

        # Stage 1: cheap triage (skip if disabled)
        if settings.llm_triage_enabled:
            if not _is_actionable(msg.sender, msg.title, (body or "")[:300]):
                log.info("extraction_skipped_triage", message_id=message_id, sender=msg.sender)
                _record_triage_skip(db, message_id, prompt_version)
                return True

        msg_data = {
            "user_id": str(msg.user_id),
            "sender": msg.sender,
            "title": msg.title,
            "message_ts": msg.message_ts.isoformat(),
            "is_canvas": msg.is_canvas,
        }

    user_prompt = USER_TEMPLATE.format(
        timezone=settings.user_timezone,
        source_type=source_type,
        sender=msg_data["sender"],
        title=msg_data["title"],
        message_ts=msg_data["message_ts"],
        body=body[:3000],
    )

    extraction: ExtractionResult | None = None
    failed = False
    failed_reason: str | None = None

    for attempt in range(1, 3):  # attempt 1 = first try, attempt 2 = repair
        prompt = user_prompt if attempt == 1 else (
            f"The previous JSON was invalid. Output ONLY valid JSON.\n\n{user_prompt}"
        )
        t0 = time.monotonic()
        try:
            raw, in_tok, out_tok = _call_llm(SYSTEM_PROMPT, prompt)
            latency_ms = int((time.monotonic() - t0) * 1000)
            extraction = _validate(raw)
            with get_db() as db:
                _record_run(db, message_id, prompt_version, attempt,
                            in_tok, out_tok, latency_ms, True, None)
            log.info("extraction_succeeded", message_id=message_id, attempt=attempt)
            break  # success
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            failed_reason = str(exc)[:500]
            log.warning(
                "extraction_attempt_failed",
                message_id=message_id,
                attempt=attempt,
                error=failed_reason,
            )
            with get_db() as db:
                _record_run(db, message_id, prompt_version, attempt,
                            0, 0, latency_ms, False, failed_reason)
            if attempt == 2:
                failed = True

    # Write results
    with get_db() as db:
        summary = MessageSummary(
            message_id=message_id,
            prompt_version=prompt_version,
            summary_short=extraction.summary_short if extraction else "Extraction failed",
            summary_long=extraction.summary_long if extraction else None,
            urgency=extraction.urgency if extraction else 0.5,
            extraction_failed=failed,
        )
        db.add(summary)
        db.flush()

        if extraction:
            for lbl in extraction.labels:
                try:
                    with db.begin_nested():  # SAVEPOINT — rollback only this label on conflict
                        db.add(MessageLabel(
                            message_id=message_id,
                            prompt_version=prompt_version,
                            label=lbl.label,
                            confidence=lbl.confidence,
                        ))
                except Exception:
                    pass  # UniqueConstraint — label already recorded for this version

            for draft in extraction.reply_drafts:
                db.add(ReplyDraft(
                    message_id=message_id,
                    prompt_version=prompt_version,
                    tone=draft.tone,
                    draft_text=draft.draft_text,
                ))

            for item in extraction.action_items:
                db.add(ActionItem(
                    user_id=msg_data["user_id"],
                    message_id=message_id,
                    title=item.title,
                    details=item.details,
                    due_at=item.due_at,
                    priority=item.priority,
                    confidence=item.confidence,
                    status="proposed",
                ))

        db.commit()
        log.info(
            "extraction_saved",
            message_id=message_id,
            prompt_version=prompt_version,
            failed=failed,
            action_items=len(extraction.action_items) if extraction else 0,
        )

    # Push Telegram notification for high-priority tasks (fail-soft)
    if extraction:
        settings2 = get_settings()
        from core.telegram_notify import send_task_notification
        for item in extraction.action_items:
            if item.priority >= settings2.bot_notify_min_priority:
                try:
                    with get_db() as db:
                        saved = db.query(ActionItem).filter_by(
                            user_id=msg_data["user_id"],
                            title=item.title,
                            status="proposed",
                        ).order_by(ActionItem.created_at.desc()).first()
                        saved_id = str(saved.id) if saved else None
                        saved_due = saved.due_at if saved else None
                    if saved_id:
                        send_task_notification(
                            task_id=saved_id,
                            title=item.title,
                            priority=item.priority,
                            due_at=saved_due,
                        )
                except Exception as exc:
                    log.warning("task_notify_lookup_failed", error=str(exc))

    return not failed


def extract_all_pending(prompt_version: str = "v1") -> tuple[int, int]:
    """
    Extract all messages that don't have a summary at this prompt_version.
    Returns (success_count, failure_count).
    """
    with get_db() as db:
        extracted_ids: set[str] = {
            str(row.message_id)
            for row in db.query(MessageSummary.message_id).filter_by(prompt_version=prompt_version)
        }
        all_ids: list[str] = [str(row.id) for row in db.query(Message.id)]
        pending = [mid for mid in all_ids if mid not in extracted_ids]

    success, failure = 0, 0
    for mid in pending:
        if extract_message(mid, prompt_version):
            success += 1
        else:
            failure += 1
    return success, failure
