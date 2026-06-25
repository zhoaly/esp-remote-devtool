from __future__ import annotations

import uvicorn

from agent_app import app, settings


if __name__ == "__main__":
    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)
