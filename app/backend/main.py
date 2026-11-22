"""Top-level ASGI entrypoint allowing `uvicorn main:app` or `python main.py`."""

import uvicorn

from app.main import app

__all__ = ["app"]


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
