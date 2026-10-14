import json
from datetime import UTC, datetime

import pytest

from app.models import Meeting, Participant, User
from app.reports.weekly import build_weekly_report, parse_iso_week
from tests.conftest import TestingSession


def test_parse_iso_week():
    start, end, prev = parse_iso_week("2026-W40")
    # 2026-W40 Monday is 2026-09-28
    assert start == datetime(2026, 9, 28, 0, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 5, 0, 0, 0, tzinfo=UTC)
    assert prev == "2026-W39"

    with pytest.raises(ValueError):
        parse_iso_week("invalid")

    with pytest.raises(ValueError):
        parse_iso_week("2026-W55")


def test_build_weekly_report_empty():
    with TestingSession() as session:
        csv_bytes = build_weekly_report("2026-W40", db=session)
        assert isinstance(csv_bytes, bytes)
        content = csv_bytes.decode("utf-8")
        assert "Total Meetings,0,0,0" in content
        assert "Total Duration (hours),0.0,0.0,0.0h" in content


def test_build_weekly_report_with_meetings():
    with TestingSession() as session:
        # Create a user
        user = User(cognito_sub="test-sub-1", email="organizer@example.com", name="Test Organizer")
        session.add(user)
        session.flush()

        # Create participants
        p1 = Participant(name="Alice", email="alice@example.com")
        p2 = Participant(name="Bob", email="bob@example.com")
        session.add_all([p1, p2])
        session.flush()

        # Current week (2026-W40: Sept 28 - Oct 4, 2026)
        m1 = Meeting(
            title="Sprint Planning",
            starts_at=datetime(2026, 9, 28, 10, 0, 0, tzinfo=UTC),
            ends_at=datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC),
            owner_id=user.id,
            participants=[p1, p2],
        )
        m2 = Meeting(
            title="Quick Sync",
            starts_at=datetime(2026, 9, 29, 14, 0, 0, tzinfo=UTC),
            ends_at=datetime(2026, 9, 29, 14, 30, 0, tzinfo=UTC),
            owner_id=user.id,
            participants=[p1],
        )

        # Previous week (2026-W39: Sept 21 - Sept 27, 2026)
        prev_m = Meeting(
            title="Previous Retrospective",
            starts_at=datetime(2026, 9, 21, 10, 0, 0, tzinfo=UTC),
            ends_at=datetime(2026, 9, 21, 11, 0, 0, tzinfo=UTC),
            owner_id=user.id,
            participants=[p1],
        )

        session.add_all([m1, m2, prev_m])
        session.commit()

        csv_bytes = build_weekly_report("2026-W40", db=session)
        assert isinstance(csv_bytes, bytes)
        content = csv_bytes.decode("utf-8")

        # Current: 2 meetings, 2.5h; Prev: 1 meeting, 1.0h
        # Delta: +1 meeting, +1.5h
        assert "Total Meetings,2,1,+1" in content
        assert "Total Duration (hours),2.5,1.0,+1.5h" in content
        assert "Sprint Planning" in content
        assert "Quick Sync" in content
        assert "Test Organizer (organizer@example.com)" in content


def test_parse_event():
    from app.reports.lambda_handler import parse_event

    # 1. EventBridge Schedule trigger
    schedule_event = {"source": "schedule", "week": None}
    trigger, week = parse_event(schedule_event)
    assert trigger == "schedule"
    assert week.startswith("20") and "-W" in week

    # 2. SQS trigger with specific week
    sqs_event = {"Records": [{"body": '{"week": "2026-W35"}'}]}
    trigger, week = parse_event(sqs_event)
    assert trigger == "sqs"
    assert week == "2026-W35"

    # 3. S3 request notification routed through SQS
    s3_sqs_event = {
        "Records": [
            {
                "body": json.dumps(
                    {
                        "Records": [
                            {
                                "eventSource": "aws:s3",
                                "s3": {
                                    "bucket": {"name": "meetings-reports-test"},
                                    "object": {"key": "requests/2026-W42_a1b2c3d4.json"},
                                },
                            }
                        ]
                    }
                )
            }
        ]
    }
    trigger, week = parse_event(s3_sqs_event)
    assert trigger == "s3-request"
    assert week == "2026-W42"

    # 4. Direct S3 event
    direct_s3_event = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "meetings-reports-test"},
                    "object": {"key": "requests/2026-W43_xyz.json"},
                },
            }
        ]
    }
    trigger, week = parse_event(direct_s3_event)
    assert trigger == "s3-request"
    assert week == "2026-W43"
