import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

from app.reports.weekly import build_weekly_report

logger = logging.getLogger("report-builder")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger.setLevel(logging.INFO)


def get_default_previous_week() -> str:
    """Return the previous ISO week string, e.g. '2026-W40'."""
    now = datetime.now(timezone.utc)
    prev_week_date = now - timedelta(days=7)
    iso_year, iso_week, _ = prev_week_date.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def parse_event(event: dict[str, Any]) -> tuple[str, str]:
    """Parse trigger and target week from Lambda event (SQS record, EventBridge schedule, or direct).

    Returns (trigger, week).
    """
    trigger = "direct"
    week = None

    if "Records" in event and event["Records"]:
        # SQS event
        record = event["Records"][0]
        trigger = "sqs"
        body_raw = record.get("body", "{}")
        try:
            body = json.loads(body_raw)
            if isinstance(body, dict):
                # If scheduler put a message with {"source": "schedule"}
                if body.get("source") == "schedule":
                    trigger = "schedule"
                elif body.get("source"):
                    trigger = str(body["source"])
                week = body.get("week")
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(event, dict):
        if event.get("source") == "schedule" or event.get("detail-type") == "Scheduled Event":
            trigger = "schedule"
        elif event.get("source"):
            trigger = str(event["source"])
        week = event.get("week")

    if not week:
        week = get_default_previous_week()

    return trigger, week


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    trigger, week = parse_event(event)

    # Log line required for submission: showing trigger and week
    logger.info(
        "report-builder triggered [trigger=%s, week=%s]",
        trigger,
        week,
        extra={"trigger": trigger, "week": week},
    )

    bucket_name = os.environ.get("REPORTS_BUCKET")
    if not bucket_name:
        raise ValueError("Environment variable REPORTS_BUCKET is required")

    logger.info("Building report for week %s...", week)
    csv_bytes = build_weekly_report(week)

    key = f"reports/{week}.csv"
    logger.info("Uploading report (%d bytes) to s3://%s/%s...", len(csv_bytes), bucket_name, key)

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=csv_bytes,
        ContentType="text/csv",
    )

    logger.info("Report successfully uploaded: s3://%s/%s", bucket_name, key)
    return {
        "status": "success",
        "trigger": trigger,
        "week": week,
        "bucket": bucket_name,
        "key": key,
        "size": len(csv_bytes),
    }

