"""Entry point for ``uvicorn chat_service.interfaces.http.main:app``.

Also a ``__main__`` block so ``python -m chat_service.interfaces.http.main``
boots the server with sensible local defaults.
"""

from __future__ import annotations

import uvicorn

from chat_service.interfaces.http.app import app

__all__ = ["app"]


def run() -> None:
    uvicorn.run(
        "chat_service.interfaces.http.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
