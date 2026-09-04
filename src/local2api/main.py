from __future__ import annotations

import logging

from fastapi import FastAPI

from local2api.api.chat import router as chat_router
from local2api.api.meta import router as meta_router
from local2api.backends.http import HTTPBackendAdapter
from local2api.config import Settings
from local2api.context_store import ContextStore, get_context_store
from local2api.routing.router import RuleRouter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="local2api", version="0.0.1")
    app.state.router = RuleRouter(settings.complexity_words)
    app.state.backend_models = {"local": settings.local_model, "cloud": settings.cloud_model}
    app.state.backends = {
        "local": HTTPBackendAdapter("local", settings.local_url, settings.local_timeout),
        "cloud": HTTPBackendAdapter("cloud", settings.cloud_url, settings.cloud_timeout),
    }
    app.state.context_store = get_context_store(settings)
    app.include_router(chat_router)
    app.include_router(meta_router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = Settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run("local2api.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
