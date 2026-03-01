# packages/core/src/core/pvi/engine.py
from datetime import datetime, timedelta, date, timezone
from core.db.engine import get_db
from core.db.models import ActionItem, Message, PVIDailyFeature, PVIDailyScore, Policy
import structlog

log = structlog.get_logger()

REGIME_THRESHOLDS = {
    "overloaded": 75,
    "peak": 60,
    "normal": 40,
    "recovery": 0,
}

POLICY_MAP = {
    "overloaded": {"max_digest_items": 5, "escalation_level": "high",
                   "reminder_cadence": "aggressive", "auto_activate": False},
    "peak":       {"max_digest_items": 10, "escalation_level": "standard",
                   "reminder_cadence": "standard", "auto_activate": False},
    "normal":     {"max_digest_items": 15, "escalation_level": "standard",
                   "reminder_cadence": "standard", "auto_activate": False},
    "recovery":   {"max_digest_items": 20, "escalation_level": "low",
                   "reminder_cadence": "gentle", "auto_activate": False},
}


def compute_features(user_id: str, for_date: date) -> dict:
    now = datetime.combine(for_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_ago = now - timedelta(hours=24)

    with get_db() as db:
        tasks_open = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status.in_(["proposed", "active"]),
        ).count()

        tasks_overdue = db.query(ActionItem).filter(
            ActionItem.user_id == user_id,
            ActionItem.status == "active",
            ActionItem.due_at < now,
        ).count()

        incoming_24h = db.query(Message).filter(
            Message.user_id == user_id,
            Message.ingested_at >= day_ago,
        ).count()

    return {
        "tasks_open": tasks_open,
        "tasks_overdue": tasks_overdue,
        "inbox_unread": 0,  # Populated from Gmail label unread count later
        "incoming_24h": incoming_24h,
        "calendar_minutes": 0,
    }


def score_from_features(features: dict) -> tuple[int, str]:
    """Returns (score 0-100, explanation)."""
    score = 50
    explanations = []

    # Overdue tasks are high weight
    overdue = features["tasks_overdue"]
    if overdue > 0:
        add = min(overdue * 10, 25)
        score += add
        explanations.append(f"tasks_overdue={overdue} (+{add})")

    # Open tasks
    open_tasks = features["tasks_open"]
    if open_tasks > 10:
        score += 10
        explanations.append(f"tasks_open={open_tasks} (+10)")
    elif open_tasks > 5:
        score += 5
        explanations.append(f"tasks_open={open_tasks} (+5)")

    # Inbox pressure
    unread = features["inbox_unread"]
    incoming = features["incoming_24h"]
    if unread > 50 or incoming > 30:
        score += 10
        explanations.append(f"inbox_pressure: unread={unread}, incoming={incoming} (+10)")
    elif unread > 20 or incoming > 15:
        score += 5
        explanations.append(f"inbox_pressure: unread={unread}, incoming={incoming} (+5)")

    # Relief: calm state
    if overdue == 0 and open_tasks <= 3 and incoming < 5:
        score -= 10
        explanations.append("calm_state (-10)")

    score = max(0, min(100, score))
    return score, "; ".join(explanations) if explanations else "baseline"


def classify_regime(score: int) -> str:
    if score >= REGIME_THRESHOLDS["overloaded"]:
        return "overloaded"
    elif score >= REGIME_THRESHOLDS["peak"]:
        return "peak"
    elif score >= REGIME_THRESHOLDS["normal"]:
        return "normal"
    else:
        return "recovery"


def compute_pvi_daily(user_id: str, for_date: date | None = None) -> dict:
    if for_date is None:
        for_date = datetime.now(tz=timezone.utc).date()

    features = compute_features(user_id, for_date)
    score, explanation = score_from_features(features)
    regime = classify_regime(score)
    policy = POLICY_MAP[regime]

    with get_db() as db:
        # Upsert features
        feat_row = db.query(PVIDailyFeature).filter_by(user_id=user_id, date=for_date).first()
        if feat_row:
            for k, v in features.items():
                setattr(feat_row, k, v)
            feat_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            feat_row = PVIDailyFeature(user_id=user_id, date=for_date, **features)
            db.add(feat_row)

        # Upsert score
        score_row = db.query(PVIDailyScore).filter_by(user_id=user_id, date=for_date).first()
        if score_row:
            score_row.score = score
            score_row.regime = regime
            score_row.explanation = explanation
            score_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            score_row = PVIDailyScore(
                user_id=user_id, date=for_date,
                score=score, regime=regime, explanation=explanation
            )
            db.add(score_row)

        # Upsert policy
        pol_row = db.query(Policy).filter_by(user_id=user_id, date=for_date).first()
        if pol_row:
            for k, v in policy.items():
                setattr(pol_row, k, v)
            pol_row.computed_at = datetime.now(tz=timezone.utc)
        else:
            pol_row = Policy(user_id=user_id, date=for_date, regime=regime, **policy)
            db.add(pol_row)

        db.commit()
        log.info("pvi_computed", user_id=user_id, date=str(for_date),
                 score=score, regime=regime)

    return {"score": score, "regime": regime, "explanation": explanation,
            "features": features, "policy": policy}
