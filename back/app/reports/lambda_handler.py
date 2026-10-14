import json
import logging
import os
import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None

from app.reports.weekly import build_weekly_report

logger = logging.getLogger("report-builder")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger.setLevel(logging.INFO)


def get_default_previous_week() -> str:
    """Return the previous ISO week string, e.g. '2026-W40'."""
    now = datetime.now(UTC)
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
        record = event["Records"][0]
        # Direct S3 event
        if record.get("eventSource") == "aws:s3":
            trigger = "s3-request"
            s3_info = record.get("s3", {})
            s3_key = urllib.parse.unquote_plus(s3_info.get("object", {}).get("key", ""))
            match = re.search(r"requests/(20\d\d-W\d\d)", s3_key)
            if match:
                week = match.group(1)
        else:
            # SQS event
            trigger = "sqs"
            body_raw = record.get("body", "{}")
            try:
                body = json.loads(body_raw)
                if isinstance(body, dict):
                    # S3 event notification routed through SQS
                    body_records = body.get("Records")
                    if body_records and body_records[0].get("eventSource") == "aws:s3":
                        trigger = "s3-request"
                        s3_info = body_records[0].get("s3", {})
                        s3_key = urllib.parse.unquote_plus(s3_info.get("object", {}).get("key", ""))
                        match = re.search(r"requests/(20\d\d-W\d\d)", s3_key)
                        if match:
                            week = match.group(1)
                        else:
                            s3_bucket = s3_info.get("bucket", {}).get("name")
                            if s3_bucket and s3_key:
                                s3_client = boto3.client("s3")
                                resp = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
                                req_json = json.loads(resp["Body"].read().decode("utf-8"))
                                week = req_json.get("week")
                    elif body.get("source") == "schedule":
                        trigger = "schedule"
                    elif body.get("source"):
                        trigger = str(body["source"])
                    else:
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
