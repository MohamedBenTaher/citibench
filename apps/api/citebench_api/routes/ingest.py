"""POST /ingest (frozen-manifest ingest; wipe requires CITEBENCH_ALLOW_WIPE=1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import database_unavailable_detail, is_database_error
from pipeline import IngestBusy, WipeDisabled, run_ingest
from routes.errors import runtime_http_error
from settings import load_settings

router = APIRouter()


class IngestRequest(BaseModel):
    wipe: bool = False
    simulate_failure_id: str | None = Field(
        default=None,
        description="Optional MANIFEST id to record as an unreachable snapshot (verification).",
    )


@router.post("/ingest")
def post_ingest(body: IngestRequest | None = None) -> dict[str, Any]:
    req = body or IngestRequest()
    settings = load_settings()
    try:
        return run_ingest(
            settings,
            wipe=req.wipe,
            simulate_failure_id=req.simulate_failure_id,
        )
    except WipeDisabled as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except IngestBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise runtime_http_error(exc) from exc
    except Exception as exc:
        if is_database_error(exc):
            raise HTTPException(
                status_code=503,
                detail=database_unavailable_detail(exc, settings.database_url),
            ) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc
