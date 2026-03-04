"""
Canvas email-bridge parser.
Detects Canvas notification emails in Gmail and extracts structured fields.
NUS-tuned: canvas.nus.edu.sg, NUS course code format [A-Z]{2,3}\\d{4}[A-Z]?
"""
import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

CANVAS_SENDER_PATTERNS: list[str] = [
    r"instructure\.com",
    r"canvas\.nus\.edu\.sg",
    r"canvas\..*\.edu",
    r"notifications@.*canvas",
    r"no-reply@.*instructure",
    r".*@nus\.edu\.sg",
]

CANVAS_SUBJECT_KEYWORDS: list[str] = [
    "assignment",
    "announcement",
    "canvas",
    "due",
    "submission",
    "course",
    "quiz",
    "grade",
    "graded",
]

# NUS course codes: CS3230, MA1101R, GEA1000N, IS4010S, etc.
COURSE_CODE_PATTERNS: list[str] = [
    r"\b([A-Z]{2,3}\d{4}[A-Z]?)\b",        # NUS format (primary)
    r"course[:\s]+([A-Z]{2,3}\d{4}[A-Z]?)", # explicit prefix
]

DUE_DATE_PATTERNS: list[str] = [
    r"[Dd]ue[:\s]+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",               # ISO 8601
    r"[Dd]ue[:\s]+([A-Z][a-z]+ \d{1,2},? \d{4}[,\s]+\d{1,2}:\d{2}\s*[APap][Mm]?)",  # Mar 9, 2026 11:59pm
    r"[Dd]ue[:\s]+([A-Z][a-z]+ \d{1,2},? \d{4})",                        # Mar 9, 2026
    r"[Dd]ue[:\s]+(\d{1,2}/\d{1,2}/\d{4}[\s,]+\d{1,2}:\d{2}\s*[APap][Mm]?)",
    r"[Dd]ue(?:\s+by)?[:\s]+([A-Z][a-z]+ \d{1,2}(?:st|nd|rd|th)?)",
]

# Matches Canvas resource URLs (assignments, quizzes, announcements)
CANVAS_URL_RE = re.compile(
    r"https?://[^\s<>\"]+(?:assignments|courses|quizzes|announcements)[^\s<>\"]*"
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CanvasParseResult:
    is_canvas: bool
    course_code: Optional[str]
    assignment_title: Optional[str]
    due_at_raw: Optional[str]
    canvas_url: Optional[str]
    canvas_type: Optional[str]  # assignment | announcement | quiz | grade


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_canvas_email(sender: str, subject: str, body: str) -> bool:
    """Return True if the email appears to be a Canvas notification."""
    sender_match = any(re.search(p, sender, re.IGNORECASE) for p in CANVAS_SENDER_PATTERNS)
    subject_match = any(kw in subject.lower() for kw in CANVAS_SUBJECT_KEYWORDS)
    body_match = "canvas" in body.lower() or "instructure" in body.lower()
    return sender_match or (subject_match and body_match)


def parse_canvas_email(sender: str, subject: str, body: str) -> CanvasParseResult:
    """
    Parse a Canvas notification email.
    Returns CanvasParseResult with is_canvas=False if not a Canvas email.
    """
    if not is_canvas_email(sender, subject, body):
        return CanvasParseResult(
            is_canvas=False,
            course_code=None,
            assignment_title=None,
            due_at_raw=None,
            canvas_url=None,
            canvas_type=None,
        )

    full_text = f"{subject}\n{body}"

    # --- Canvas type ---
    canvas_type: Optional[str] = None
    lower = full_text.lower()
    if "announcement" in lower:
        canvas_type = "announcement"
    elif "quiz" in lower or "exam" in lower:
        canvas_type = "quiz"
    elif any(w in lower for w in ("grade", "graded", "scored", "score")):
        canvas_type = "grade"
    else:
        canvas_type = "assignment"

    # --- Course code ---
    course_code: Optional[str] = None
    for pattern in COURSE_CODE_PATTERNS:
        m = re.search(pattern, full_text)
        if m:
            course_code = m.group(1).strip()
            break

    # --- Due date ---
    due_at_raw: Optional[str] = None
    for pattern in DUE_DATE_PATTERNS:
        m = re.search(pattern, full_text)
        if m:
            due_at_raw = m.group(1).strip()
            break

    # --- Canvas URL ---
    url_match = CANVAS_URL_RE.search(body)
    canvas_url: Optional[str] = url_match.group(0) if url_match else None

    # --- Assignment title (from subject) ---
    assignment_title: Optional[str] = None
    for prefix_re in [
        r"[Aa]ssignment(?:\s+due)?[:\s]+(.+?)(?:\s+[Dd]ue|\s*$)",
        r"[Nn]ew [Aa]ssignment for [A-Z]{2,3}\d{4}[A-Z]?[:\s]+(.+)",
        r"[Ss]ubmission[:\s]+(.+?)(?:\s+[Dd]ue|\s*$)",
        r"[Qq]uiz[:\s]+(.+?)(?:\s+[Dd]ue|\s*$)",
    ]:
        m = re.search(prefix_re, subject)
        if m:
            assignment_title = m.group(1).strip()
            break
    if not assignment_title:
        assignment_title = subject.strip() or None

    return CanvasParseResult(
        is_canvas=True,
        course_code=course_code,
        assignment_title=assignment_title,
        due_at_raw=due_at_raw,
        canvas_url=canvas_url,
        canvas_type=canvas_type,
    )
