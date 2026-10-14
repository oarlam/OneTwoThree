import csv
import io
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from app.db import SessionLocal
from app.models import Meeting, User


def parse_iso_week(week_str: str) -> tuple[datetime, datetime, str]:
    """Parse an ISO week string like '2026-W40' into (start_of_week, start_of_next_week, prev_week_str).

    All returned datetimes are UTC timezone-aware.
    """
    match = re.match(r"^(\d{4})-W(\d{2})$", week_str.strip())
    if not match:
        raise ValueError(f"Invalid ISO week format: '{week_str}'. Expected format like '2026-W40'.")

    year = int(match.group(1))
    week = int(match.group(2))

    if week < 1 or week > 53:
        raise ValueError(f"Invalid ISO week number: {week}. Must be between 1 and 53.")

    # Monday 00:00:00 UTC
    start_of_week = datetime.fromisocalendar(year, week, 1).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC
    )
    start_of_next_week = start_of_week + timedelta(days=7)

    # Previous ISO week
    start_of_prev_week = start_of_week - timedelta(days=7)
    prev_iso_year, prev_iso_week, _ = start_of_prev_week.isocalendar()
    prev_week_str = f"{prev_iso_year}-W{prev_iso_week:02d}"

    return start_of_week, start_of_next_week, prev_week_str


def build_weekly_report(week: str, db: Session | None = None) -> bytes:
    """Query the meetings of one ISO week (e.g. '2026-W40') and return the CSV as bytes.

    Includes:
      - Number of meetings and total duration in hours for the week
      - The same two numbers for the week before and the delta
      - The five longest meetings (title, start, duration, participant count)
      - Breakdown by organizer/user
    """
    start_of_week, start_of_next_week, prev_week_str = parse_iso_week(week)
    start_of_prev_week = start_of_week - timedelta(days=7)

    def _generate(session: Session) -> bytes:
        # Load meetings with participants and owner for current and previous weeks
        curr_meetings = (
            session.query(Meeting)
            .options(joinedload(Meeting.participants))
            .filter(Meeting.starts_at >= start_of_week, Meeting.starts_at < start_of_next_week)
            .all()
        )

        prev_meetings = (
            session.query(Meeting)
            .filter(Meeting.starts_at >= start_of_prev_week, Meeting.starts_at < start_of_week)
            .all()
        )

        def meeting_duration_hours(m: Meeting) -> float:
            if m.ends_at and m.starts_at and m.ends_at > m.starts_at:
                return (m.ends_at - m.starts_at).total_seconds() / 3600.0
            return 0.0

        curr_count = len(curr_meetings)
        curr_hours = sum(meeting_duration_hours(m) for m in curr_meetings)

        prev_count = len(prev_meetings)
        prev_hours = sum(meeting_duration_hours(m) for m in prev_meetings)

        count_change = curr_count - prev_count
        hours_change = curr_hours - prev_hours

        # Top 5 longest meetings
        sorted_meetings = sorted(curr_meetings, key=meeting_duration_hours, reverse=True)[:5]

        # Breakdown per organizer
        organizer_stats: dict[str, dict[str, float | int]] = {}
        users_by_id = {u.id: u for u in session.query(User).all()}

        for m in curr_meetings:
            dur = meeting_duration_hours(m)
            owner = users_by_id.get(m.owner_id) if m.owner_id else None
            if owner and owner.name:
                org_label = f"{owner.name} ({owner.email})"
            elif owner:
                org_label = owner.email
            else:
                org_label = "Unassigned"

            if org_label not in organizer_stats:
                organizer_stats[org_label] = {"count": 0, "hours": 0.0}
            organizer_stats[org_label]["count"] += 1
            organizer_stats[org_label]["hours"] += dur

        # Format CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Section 1: Summary
        writer.writerow(["SUMMARY", f"Week {week}", f"Week {prev_week_str}", "Change"])
        count_change_str = f"+{count_change}" if count_change > 0 else str(count_change)
        hours_change_str = f"+{hours_change:.1f}h" if hours_change > 0 else f"{hours_change:.1f}h"
        writer.writerow(["Total Meetings", str(curr_count), str(prev_count), count_change_str])
        writer.writerow(
            ["Total Duration (hours)", f"{curr_hours:.1f}", f"{prev_hours:.1f}", hours_change_str]
        )
        writer.writerow([])

        # Section 2: Top 5 Longest Meetings
        writer.writerow(["TOP 5 LONGEST MEETINGS"])
        writer.writerow(["Title", "Start Time (UTC)", "Duration (hours)", "Participants Count"])
        if not sorted_meetings:
            writer.writerow(["No meetings this week", "", "", ""])
        else:
            for m in sorted_meetings:
                dur = meeting_duration_hours(m)
                starts_str = m.starts_at.strftime("%Y-%m-%d %H:%M UTC") if m.starts_at else ""
                part_count = len(m.participants) if m.participants else 0
                writer.writerow([m.title, starts_str, f"{dur:.2f}", str(part_count)])
        writer.writerow([])

        # Section 3: Breakdown by Organizer
        writer.writerow(["BREAKDOWN BY ORGANIZER"])
        writer.writerow(["Organizer", "Meetings Count", "Total Duration (hours)"])
        if not organizer_stats:
            writer.writerow(["No data", "0", "0.0"])
        else:
            sorted_orgs = sorted(
                organizer_stats.items(),
                key=lambda item: item[1]["hours"],
                reverse=True,
            )
            for org_label, stats in sorted_orgs:
                writer.writerow([org_label, str(stats["count"]), f"{stats['hours']:.2f}"])

        return output.getvalue().encode("utf-8")

    if db is not None:
        return _generate(db)
    with SessionLocal() as session:
        return _generate(session)
