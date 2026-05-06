import os
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from database import init_db

app = FastAPI(title="MyFans Affiliate Control Tower")

templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

# DB初期化
init_db()

# ルーター登録
from routers.dashboard import router as dashboard_router
from routers.creators import router as creators_router
from routers.links import router as links_router
from routers.drafts import router as drafts_router
from routers.reports import router as reports_router
from routers.settings import router as settings_router
from routers.compliance_router import router as compliance_router
from routers.calendar_router import router as calendar_router
from routers.importer import router as importer_router
from routers.link_queue import router as link_queue_router
from routers.assets import router as assets_router
from routers.cards import router as cards_router
from routers.auto_import import router as auto_import_router

app.include_router(dashboard_router)
app.include_router(creators_router)
app.include_router(links_router)
app.include_router(drafts_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(compliance_router)
app.include_router(calendar_router)
app.include_router(importer_router)
app.include_router(link_queue_router)
app.include_router(assets_router)
app.include_router(cards_router)
app.include_router(auto_import_router)


@app.get("/")
async def root():
    return RedirectResponse("/dashboard")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
