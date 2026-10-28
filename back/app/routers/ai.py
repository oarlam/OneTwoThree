from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.agenda import PROMPT_VERSION, AgendaParseError, parse_agenda
from app.auth import get_current_user
from app.config import settings
from app.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    today: date | None = None
    tz: str = "Europe/Kyiv"


@router.post("/parse")
def parse(
    req: ParseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    today = req.today or date.today()
    try:
        agenda, usage = parse_agenda(req.text, today, req.tz)
    except AgendaParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        err_msg = str(exc)
        if "rate" in err_msg.lower() or "throttl" in err_msg.lower() or "429" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bedrock service is busy (throttling), please try again shortly",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to call Bedrock: {err_msg}",
        ) from exc

    return {
        "agenda": agenda.model_dump(mode="json"),
        "model": settings.parser_model,
        "prompt_version": PROMPT_VERSION,
    }
