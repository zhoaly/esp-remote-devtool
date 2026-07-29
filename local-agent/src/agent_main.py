from __future__ import annotations

import multiprocessing

import uvicorn

from agent_app import app, settings


if __name__ == "__main__":
    multiprocessing.freeze_support()
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)
