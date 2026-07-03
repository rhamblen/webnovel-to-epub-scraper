"""Liveness/readiness probe."""
from fastapi import APIRouter
from sqlmodel import Session, select

from ..db import get_engine
from ..models import Setting

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict:
    try:
        with Session(get_engine()) as s:
            s.exec(select(Setting)).first()
        return {"status": "ok", "db": "ok"}
    except Exception:
        return {"status": "degraded", "db": "error"}
