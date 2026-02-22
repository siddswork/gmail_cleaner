"""
FastAPI application entry point.

Run with:
    uvicorn backend.main:app --reload --port 8000
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import auth, cleanup, dashboard, insights, sync, unsubscribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: auto-load any existing account tokens
    from auth.oauth import _data_root, get_authenticated_service
    from backend import state
    from cache.database import init_db

    root = _data_root()
    if root.exists():
        for d in sorted(root.iterdir()):
            if d.is_dir() and (d / "token.json").exists():
                email = d.name
                try:
                    svc = get_authenticated_service(email)
                    state.gmail_services[email] = svc
                    init_db(email)
                    print(f"[startup] Loaded account: {email}")
                except Exception as e:
                    print(f"[startup] Failed to load {email}: {e}")

    yield
    # Shutdown: nothing to clean up (threads are daemons)


app = FastAPI(
    title="Gmail Cleaner API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(sync.router)
app.include_router(dashboard.router)
app.include_router(cleanup.router)
app.include_router(unsubscribe.router)
app.include_router(insights.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
