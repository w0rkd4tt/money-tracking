import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .db import ensure_db_ready
from .routers import (
    accounts,
    admin,
    buckets,
    budgets,
    categories,
    chat,
    dashboard,
    gmail,
    health,
    llm_providers,
    llm_policies,
    oauth,
    plans,
    settings as settings_router,
    transactions,
    transfers,
    ui_passkey,
    ui_unlock,
)
from .schedulers.jobs import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await ensure_db_ready()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="Money Tracking API",
    version=__version__,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan,
)

# CORS: local dev only, permissive for web at :3000 on same host.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(health.router, prefix=API)
app.include_router(ui_unlock.router, prefix=API)
app.include_router(ui_passkey.router, prefix=API)
app.include_router(accounts.router, prefix=API)
app.include_router(categories.router, prefix=API)
app.include_router(transactions.router, prefix=API)
app.include_router(transfers.router, prefix=API)
app.include_router(budgets.router, prefix=API)
app.include_router(buckets.router, prefix=API)
app.include_router(plans.router, prefix=API)
app.include_router(dashboard.router, prefix=API)
app.include_router(chat.router, prefix=API)
app.include_router(settings_router.router, prefix=API)
app.include_router(llm_providers.router, prefix=API)
app.include_router(llm_policies.router, prefix=API)
app.include_router(oauth.router, prefix=API)
app.include_router(gmail.router, prefix=API)
app.include_router(admin.router, prefix=API)


@app.get("/")
async def root():
    s = get_settings()
    return {
        "name": "Money Tracking API",
        "version": __version__,
        "docs": f"{API}/docs",
        "timezone": s.tz,
    }
