from __future__ import annotations

import uvicorn

from rag_platform.api.app import create_application
from rag_platform.config import load_settings


def run() -> None:
    settings = load_settings()
    uvicorn.run(
        create_application(settings),
        host=settings.api.host,
        port=settings.api.port,
    )
