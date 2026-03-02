"""Google Calendar connector — polls next 14 days of events."""
from datetime import datetime, timezone, timedelta

import structlog
from googleapiclient.discovery import build

from connectors.gmail.auth import get_credentials
from core.db.engine import get_db
from core.db.models import CalendarEvent, Source
from core.config import get_settings

log = structlog.get_logger()


def _parse_event_fields(event: dict) -> dict:
    start = event.get("start", {})
    end = event.get("end", {})
    is_all_day = "date" in start and "dateTime" not in start

    def parse_dt(dt_dict: dict) -> datetime:
        if "dateTime" in dt_dict:
            return datetime.fromisoformat(dt_dict["dateTime"]).astimezone(timezone.utc)
        # all-day: use midnight UTC
        d = dt_dict["date"]
        return datetime.fromisoformat(d + "T00:00:00+00:00")

    return {
        "external_id": event["id"],
        "title": event.get("summary", "(no title)"),
        "start_at": parse_dt(start),
        "end_at": parse_dt(end),
        "location": event.get("location"),
        "attendees_json": [a.get("email") for a in event.get("attendees", [])],
        "description": event.get("description"),
        "is_all_day": is_all_day,
    }


def poll_gcal(user_id: str, source_id: str) -> int:
    """Fetch events for next 14 days. Upsert CalendarEvent rows. Returns insert count."""
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(tz=timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=14)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()

    events = events_result.get("items", [])
    inserted = 0

    for event in events:
        if event.get("status") == "cancelled":
            continue
        fields = _parse_event_fields(event)
        with get_db() as db:
            existing = db.query(CalendarEvent).filter_by(
                user_id=user_id, external_id=fields["external_id"]
            ).first()
            if existing:
                for k, v in fields.items():
                    if k != "external_id":
                        setattr(existing, k, v)
                db.commit()
            else:
                db.add(CalendarEvent(user_id=user_id, source_id=source_id, **fields))
                db.commit()
                inserted += 1

    log.info("gcal_poll_complete", inserted=inserted, total=len(events), user_id=user_id)
    return inserted
