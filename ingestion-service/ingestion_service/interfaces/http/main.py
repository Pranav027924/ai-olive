"""Entry point for the ingestion service.

``python -m ingestion_service.interfaces.http.main`` boots uvicorn on
the configured host/port (default 127.0.0.1:8001).
"""

from __future__ import annotations

import uvicorn

from ingestion_service.config import IngestionSettings
from ingestion_service.interfaces.http.app import app

__all__ = ["app"]


def run() -> None:
    settings = IngestionSettings()
    uvicorn.run(
        "ingestion_service.interfaces.http.main:app",
        host=settings.http_host,
        port=settings.http_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
