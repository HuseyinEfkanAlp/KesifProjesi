from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import catalog, drawings, pricebook, prices, projects, quantities, reports
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    try:
        from .services import cleanup_uploads
        cleanup_uploads()      # seçilmeden bırakılan kaynak dosyalar (src_*.dxf, 500 MB'a kadar) 24 saat sonra silinir
    except Exception:
        pass
    yield


app = FastAPI(title="Keşif - DXF Metraj ve Maliyet", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (projects.router, drawings.router, quantities.router, prices.router, pricebook.router, reports.router,
          catalog.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    from .parser.dwg import dwg_supported
    return {"status": "ok", "dwg_support": dwg_supported()}


# Üretimde: frontend/dist derlenmişse aynı sunucudan servis et
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = (DIST / full_path).resolve()
        if full_path and f.is_file() and f.is_relative_to(DIST.resolve()):
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
