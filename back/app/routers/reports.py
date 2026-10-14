import json
import logging
import uuid
from datetime import UTC, datetime

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import settings
from app.models import User
from app.reports.weekly import parse_iso_week

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger(__name__)


class ReportRequestPayload(BaseModel):
    week: str | None = Field(
        default=None,
        description="Target ISO week (e.g. '2026-W42'). Defaults to current ISO week.",
        examples=["2026-W42"],
    )


class ReportRequestResponse(BaseModel):
    status: str
    week: str
    request_id: str
    message: str


def get_current_iso_week() -> str:
    """Return the current ISO week string, e.g. '2026-W42'."""
    now = datetime.now(UTC)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


@router.post("/request", response_model=ReportRequestResponse)
def request_weekly_report(
    payload: ReportRequestPayload | None = None,
    user: User = Depends(get_current_user),
):
    """Request a weekly report to be generated and emailed.

    Writes a request marker file to S3 (`requests/<week>_<id>.json`) through the VPC
    S3 Gateway Endpoint, which triggers the event-driven report generator via SQS.
    """
    target_week = (payload.week if payload and payload.week else "").strip()
    if not target_week:
        target_week = get_current_iso_week()
    else:
        try:
            parse_iso_week(target_week)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    request_id = uuid.uuid4().hex[:8]
    req_filename = f"requests/{target_week}_{request_id}.json"

    bucket = settings.reports_bucket
    if bucket:
        try:
            s3 = boto3.client("s3")
            request_data = {
                "request_id": request_id,
                "week": target_week,
                "requested_by": user.email,
                "requested_at": datetime.now(UTC).isoformat(),
            }
            s3.put_object(
                Bucket=bucket,
                Key=req_filename,
                Body=json.dumps(request_data).encode("utf-8"),
                ContentType="application/json",
            )
            logger.info(
                "Created report request in S3: s3://%s/%s for week %s by %s",
                bucket,
                req_filename,
                target_week,
                user.email,
            )
        except Exception as exc:
            logger.error("Failed to write report request to S3: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to submit report request: {exc}",
            ) from exc
    else:
        logger.info(
            "REPORTS_BUCKET not set. Simulated report request %s for %s",
            request_id,
            target_week,
        )

    return ReportRequestResponse(
        status="queued",
        week=target_week,
        request_id=request_id,
        message=f"Report request for {target_week} accepted and queued.",
    )
