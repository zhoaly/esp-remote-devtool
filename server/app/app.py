"""Compatibility import for Python callers; HTTP V1 routes were removed in 0.2.0."""

from app.main import app, create_app

__all__ = ["app", "create_app"]
