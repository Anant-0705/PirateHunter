from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from piratehunt.api.routers import (
    dashboard,
    discovery,
    health,
    matches,
    rights_holders,
    takedowns,
    verification,
)
from piratehunt.api.realtime.endpoint import router as realtime_router

app = FastAPI(
    title="PirateHunt",
    description="Real-time live-stream piracy detection for sports broadcasts",
    version="0.1.0",
)

# Enable CORS for dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(discovery.router)
app.include_router(matches.router)
app.include_router(verification.router)
app.include_router(takedowns.router)
app.include_router(rights_holders.router)
app.include_router(dashboard.router)
app.include_router(realtime_router)
