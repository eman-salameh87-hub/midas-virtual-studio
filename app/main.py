"""FastAPI shell for the MIDAS backend."""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.jobs import router

load_dotenv()

app = FastAPI(title="midas-backend")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
