import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import require_env_ok, settings
from database import Database
from userbot_manager import UserbotManager
from bot import run_service_bot

require_env_ok()

app = FastAPI(title="Userbot SaaS")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

db = Database()
userbots = UserbotManager(db=db)
bot_instance = None


@app.on_event("startup")
async def on_startup():
    global bot_instance
    await db.connect()
    await userbots.start()
    bot_instance = await run_service_bot(db, userbots)
    await db.add_log(0, "INFO", "Web service started")

@app.on_event("shutdown")
async def on_shutdown():
    global bot_instance
    try:
        if bot_instance:
            await bot_instance.stop()
    except Exception:
        pass
    try:
        await userbots.stop()
    except Exception:
        pass
    await db.close()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "base": settings.PUBLIC_BASE_URL})


@app.get("/api/logs")
async def api_logs(limit: int = 200):
    logs = await db.list_logs(limit=limit)
    return JSONResponse({"ok": True, "logs": logs})
