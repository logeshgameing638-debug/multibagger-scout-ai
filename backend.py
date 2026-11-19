"""Start the FastAPI backend: python backend.py  (or run_backend.bat)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("backend.api:app", host=settings.backend_host, port=settings.backend_port)


if __name__ == "__main__":
    main()
