"""Uvicorn entry point: the app is assembled in the routes package."""

from __future__ import annotations

from citebench_api.routes import create_app

app = create_app()
