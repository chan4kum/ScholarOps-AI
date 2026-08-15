from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from opportunity_intel.config import Settings, get_settings
from opportunity_intel.db import init_db
from opportunity_intel.llm.models_config import load_model_config
from opportunity_intel.observability.trace import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()
    init_db(settings)
    model_config = load_model_config(settings.models_config_path)

    app = FastAPI(title="ScholarOps AI", version="0.1.0")
    app.state.settings = settings
    app.state.model_config = model_config
    app.state.sandbox_inbox = []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from opportunity_intel.api.routes import router

    app.include_router(router)
    return app
