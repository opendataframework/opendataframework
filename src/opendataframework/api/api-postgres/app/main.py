"""Main module."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings
from app.database import init_db
from app.models import HealthCheck
from app.router import entity_router

app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    debug=settings.debug,
)


origins = ["http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_entity():
    """Init database on startup."""
    init_db()


@app.get("/", response_model=HealthCheck, tags=["status"])
async def health_check():
    """Health check."""
    return {
        "name": settings.project_name,
        "version": settings.version,
        "description": settings.description,
    }


app.include_router(entity_router, prefix=settings.api_v1_prefix)
