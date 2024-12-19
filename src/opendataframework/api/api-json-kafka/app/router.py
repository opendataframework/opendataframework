"""Router module."""

from fastapi import APIRouter, status

from app.crud import post_entity
from app.models import Entity

entity_router = APIRouter(prefix="/entities", tags=["entities"])


@entity_router.post("/", response_model=Entity, status_code=status.HTTP_201_CREATED)
async def create_entity(entity: Entity):
    """Create entity."""
    entity = await post_entity(entity)
    return entity
