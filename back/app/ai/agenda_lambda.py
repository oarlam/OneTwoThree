import base64
import json
import logging
import time
from datetime import date
from typing import Any

from app.ai.agenda import PROMPT_VERSION, AgendaParseError, cost_usd, parse_agenda
from app.auth import LOCAL_IDENTITY, verify_id_token
from app.config import settings

logger = logging.getLogger("app.ai.agenda")
logger.setLevel(logging.INFO)

CORS_HEADERS = {
    "content-type": "application/json",
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "authorization, content-type",
}


def _response(status_code: int, body_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body_data, ensure_ascii=False),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # Handle CORS preflight if invoked directly
    method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod")
    if method == "OPTIONS":
        return _response(200, {"ok": True})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    auth_header = headers.get("authorization", "")

    # Authenticate via Cognito ID token (or LOCAL_IDENTITY when auth is disabled)
    if settings.auth_enabled:
        if not auth_header or not auth_header.startswith("Bearer "):
            return _response(401, {"error": "Missing or invalid Authorization header"})
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            user = verify_id_token(token)
        except Exception as exc:
            return _response(401, {"error": f"Unauthorized: {exc}"})
    else:
        user = LOCAL_IDENTITY

    raw_body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        body = json.loads(raw_body)
    except Exception:
        return _response(400, {"error": "Invalid JSON body"})

    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return _response(400, {"error": "Field 'text' is required and must not be empty"})

    # Limits: Reject text longer than 10,000 characters with 413 before calling the model
    if len(text) > 10_000:
        return _response(413, {"error": "Text exceeds maximum allowed length of 10,000 characters"})

    today_str = body.get("today")
    tz = body.get("tz") or "Europe/Kyiv"

    try:
        today_date = date.fromisoformat(today_str) if today_str else date.today()
    except ValueError:
        return _response(400, {"error": "Invalid date format for 'today' (expected ISO YYYY-MM-DD)"})

    started = time.monotonic()
    try:
        agenda, usage = parse_agenda(text, today_date, tz)
    except AgendaParseError as exc:
        return _response(422, {"error": str(exc)})
    except Exception as exc:
        err_msg = str(exc)
        if "rate" in err_msg.lower() or "throttl" in err_msg.lower() or "429" in err_msg:
            return _response(429, {"error": "Bedrock service is busy (throttling), please try again shortly"})
        return _response(502, {"error": f"Failed to call Bedrock: {err_msg}"})

    latency_ms = int((time.monotonic() - started) * 1000)
    calculated_cost = cost_usd(settings.parser_model, usage)

    log_payload = {
        "event": "agenda_parsed",
        "user": user.sub,
        "model": settings.parser_model,
        "prompt_version": PROMPT_VERSION,
        **usage,
        "latency_ms": latency_ms,
        "cost_usd": calculated_cost,
    }
    logger.info(json.dumps(log_payload))

    return _response(
        200,
        {
            "agenda": agenda.model_dump(mode="json"),
            "model": settings.parser_model,
            "prompt_version": PROMPT_VERSION,
        },
    )
