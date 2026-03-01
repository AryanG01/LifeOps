# apps/api/src/api/main.py
from fastapi import FastAPI
from api.routes import inbox, tasks, digest, pvi, sync, replay

app = FastAPI(title="Clawdbot Life Ops API", version="0.1.0")

app.include_router(sync.router, prefix="/v1/sync")
app.include_router(inbox.router, prefix="/v1/inbox")
app.include_router(tasks.router, prefix="/v1/tasks")
app.include_router(digest.router, prefix="/v1/digest")
app.include_router(pvi.router, prefix="/v1/pvi")
app.include_router(replay.router, prefix="/v1/replay")


@app.get("/health")
def health():
    return {"status": "ok"}
