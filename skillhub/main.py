from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from skillhub.categories import migrate_categories
from skillhub.config import settings
from skillhub.db import SessionLocal, init_db
from skillhub.marketplace import rebuild_marketplace
from skillhub.routers.auth import router as auth_router
from skillhub.routers.catalog import router as catalog_router
from skillhub.routers.skills import router as skills_router
from skillhub.seed import seed_if_empty

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    settings.ensure_dirs()
    init_db()
    db = SessionLocal()
    try:
        seed_if_empty(db)
        migrate_categories(db)
        rebuild_marketplace(db)
    finally:
        db.close()

    app = FastAPI(title=settings.org_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if FRONTEND_DIST.exists():
        index_html = (FRONTEND_DIST / "index.html").read_text(encoding="utf-8")

        @app.middleware("http")
        async def serve_frontend_root(request, call_next):
            if request.scope.get("path", "") in ("", "/"):
                return HTMLResponse(index_html)
            return await call_next(request)

        @app.get("", include_in_schema=False)
        def spa_empty_path():
            return HTMLResponse(index_html)

    app.include_router(auth_router)
    app.include_router(skills_router)
    app.include_router(catalog_router)

    @app.get("/api/health")
    def health():
        return {"ok": True, "org": settings.org_name}

    if FRONTEND_DIST.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_DIST, html=True),
            name="frontend-assets",
        )

    return app


app = create_app()
