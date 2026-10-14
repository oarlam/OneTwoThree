import email.message
import logging
import os
import urllib.parse
from typing import Any

import boto3

logger = logging.getLogger("report-mailer")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    # Extract S3 bucket and object key
    records = event.get("Records", [])
    if not records:
        logger.warning("No records found in event")
        return {"status": "no_records"}

    s3_info = records[0].get("s3", {})
    bucket = s3_info.get("bucket", {}).get("name")
    raw_key = s3_info.get("object", {}).get("key", "")
    key = urllib.parse.unquote_plus(raw_key)

    # Log line required for submission: showing trigger and key
    logger.info(
        "report-mailer triggered [trigger=s3, bucket=%s, key=%s]",
        bucket,
        key,
        extra={"trigger": "s3", "bucket": bucket, "key": key},
    )

    if not bucket or not key:
        raise ValueError(f"Invalid S3 event: bucket={bucket}, key={key}")

    # Only process CSV files inside reports/
    if not key.startswith("reports/") or not key.endswith(".csv"):
        logger.info("Skipping non-report key: %s", key)
        return {"status": "skipped", "key": key}

    sender = os.environ.get("REPORTS_FROM_EMAIL")
    recipient = os.environ.get("REPORTS_TO_EMAIL")
    if not sender or not recipient:
        raise ValueError("Environment variables REPORTS_FROM_EMAIL and REPORTS_TO_EMAIL are required")

    s3 = boto3.client("s3")
    logger.info("Downloading s3://%s/%s...", bucket, key)
    response = s3.get_object(Bucket=bucket, Key=key)
    csv_bytes = response["Body"].read()

    filename = key.split("/")[-1]
    week = filename.removesuffix(".csv")

    # Build Email Message with attachment
    msg = email.message.EmailMessage()
    msg["Subject"] = f"Weekly Meetings Report — {week}"
    msg["From"] = sender
    msg["To"] = recipient

    msg.set_content(
        f"Hello,\n\nPlease find attached the weekly meetings report for {week}.\n\n"
        f"Generated automatically by the Meetings Scheduler Event-Driven Reporting System.\n"
    )

    msg.add_attachment(
        csv_bytes,
        maintype="text",
        subtype="csv",
        filename=filename,
    )

    # Send email via SES
    ses = boto3.client("sesv2")
    logger.info("Sending report email from %s to %s via Amazon SES...", sender, recipient)
    ses_response = ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": [recipient]},
        Content={"Raw": {"Data": msg.as_bytes()}},
    )

    message_id = ses_response.get("MessageId")
    logger.info("Email sent successfully! MessageId: %s", message_id)

    return {
        "status": "success",
        "trigger": "s3",
        "key": key,
        "recipient": recipient,
        "message_id": message_id,
    }
