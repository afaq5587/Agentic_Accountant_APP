"""Application entry point for SHAHENSHA GROUP' ACCOUNTANT."""

from __future__ import annotations

import os

from dotenv import load_dotenv

from agent import create_agent
from ui import create_app


def _bootstrap_env() -> None:
    env_path = os.getenv("SHAHENSHA_ENV", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)


_bootstrap_env()

agent_bundle = create_agent()
app = create_app(agent_bundle)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
