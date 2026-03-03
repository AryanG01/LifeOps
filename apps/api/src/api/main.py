# apps/api/src/api/main.py
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from datetime import date as _date
from pathlib import Path as _Path
from api.routes import inbox, tasks, digest, pvi, sync, replay, dashboard_api

app = FastAPI(title="Clawdbot Life Ops API", version="0.1.0")
_templates = Jinja2Templates(directory=str(_Path(__file__).parent / "templates"))

app.include_router(sync.router, prefix="/v1/sync")
app.include_router(inbox.router, prefix="/v1/inbox")
app.include_router(tasks.router, prefix="/v1/tasks")
app.include_router(digest.router, prefix="/v1/digest")
app.include_router(pvi.router, prefix="/v1/pvi")
app.include_router(replay.router, prefix="/v1/replay")
app.include_router(dashboard_api.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def dashboard_home(request: Request):
    return _templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "today": _date.today().strftime("%A, %B %d %Y")},
    )


@app.get("/tasks", include_in_schema=False)
def tasks_page(request: Request):
    return _templates.TemplateResponse("tasks.html", {"request": request})


@app.get("/inbox", include_in_schema=False)
def inbox_page(request: Request):
    return _templates.TemplateResponse("inbox.html", {"request": request})
