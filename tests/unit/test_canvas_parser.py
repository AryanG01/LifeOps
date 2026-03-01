# tests/unit/test_canvas_parser.py
import pytest
from connectors.canvas.parser import parse_canvas_email, is_canvas_email

FIXTURES = [
    {
        "name": "assignment_due",
        "sender": "notifications@instructure.com",
        "subject": "Assignment due: CS3230 Problem Set 4",
        "body": (
            "Your assignment CS3230 Problem Set 4 is due Mar 9 23:59. "
            "Submit at https://canvas.nus.edu.sg/courses/123/assignments/456"
        ),
        "expect_canvas": True,
        "expect_type": "assignment",
        "expect_course": "CS3230",
        "expect_url_contains": "assignments",
    },
    {
        "name": "announcement",
        "sender": "no-reply@canvas.example.edu",
        "subject": "CS2100 Announcement: Lecture venue change",
        "body": "Announcement from CS2100: The lecture venue has changed to SR1.",
        "expect_canvas": True,
        "expect_type": "announcement",
        "expect_course": "CS2100",
        "expect_url_contains": None,
    },
    {
        "name": "grade_posted",
        "sender": "no-reply@instructure.com",
        "subject": "Grade posted for CS3230",
        "body": "Your grade has been posted for CS3230 Assignment 3. You scored 85/100.",
        "expect_canvas": True,
        "expect_type": "grade",
        "expect_course": "CS3230",
        "expect_url_contains": None,
    },
    {
        "name": "quiz_reminder",
        "sender": "notifications@instructure.com",
        "subject": "Quiz due soon: CS2040 Quiz 3",
        "body": "CS2040 Quiz 3 is due tomorrow at 09:00. Complete at https://canvas.example.edu/courses/99/quizzes/77",
        "expect_canvas": True,
        "expect_type": "quiz",
        "expect_course": "CS2040",
        "expect_url_contains": "quizzes",
    },
    {
        "name": "non_canvas_email",
        "sender": "boss@company.com",
        "subject": "Meeting tomorrow",
        "body": "Let's meet at 3pm.",
        "expect_canvas": False,
        "expect_type": None,
        "expect_course": None,
        "expect_url_contains": None,
    },
    {
        "name": "canvas_with_iso_due_date",
        "sender": "noreply@instructure.com",
        "subject": "Submission: CS4248 Project Report",
        "body": "Due: 2026-03-15T23:59:00. Submit at https://canvas.school.edu/courses/10/assignments/20",
        "expect_canvas": True,
        "expect_type": "assignment",
        "expect_course": "CS4248",
        "expect_url_contains": "assignments",
    },
    {
        "name": "nus_canvas_assignment",
        "sender": "notifications@instructure.com",
        "subject": "New Assignment for CS3230: Problem Set 3",
        "body": (
            "Due: Mar 9, 2026 11:59pm\n"
            "https://canvas.nus.edu.sg/courses/123/assignments/456"
        ),
        "expect_canvas": True,
        "expect_type": "assignment",
        "expect_course": "CS3230",
        "expect_url_contains": "canvas.nus.edu.sg",
    },
]


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_canvas_parser(fixture):
    result = parse_canvas_email(fixture["sender"], fixture["subject"], fixture["body"])
    assert result.is_canvas == fixture["expect_canvas"]
    if fixture["expect_canvas"]:
        assert result.canvas_type == fixture["expect_type"]
        if fixture["expect_course"]:
            assert result.course_code == fixture["expect_course"]
        if fixture["expect_url_contains"]:
            assert fixture["expect_url_contains"] in (result.canvas_url or "")


def test_is_canvas_email_helper():
    assert is_canvas_email("notifications@instructure.com", "Assignment: CS2100 test") is True
    assert is_canvas_email("boss@company.com", "Meeting tomorrow") is False
