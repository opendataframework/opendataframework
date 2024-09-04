"""Router module."""

import csv
from datetime import datetime
from io import BytesIO, StringIO
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.crud import get_entities, get_entity, post_entity
from app.dependencies import get_session
from app.models import Entity

entity_router = APIRouter(prefix="/entities", tags=["entities"])


@entity_router.post("/", response_model=Entity, status_code=status.HTTP_201_CREATED)
def create_entity(entity: Entity, session: Session = Depends(get_session)):
    """Create entity."""
    entity = post_entity(entity, session)
    return entity


@entity_router.get(
    "/{entity_id}", response_model=Entity, status_code=status.HTTP_200_OK
)
def read_entity(entity_id: str, session: Session = Depends(get_session)):
    """Read entity."""
    entity = get_entity(entity_id, session)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="entity not found"
        )
    return entity


@entity_router.get("/", response_model=List[Entity], status_code=status.HTTP_200_OK)
def read_entities(
    start_at: datetime, end_at: datetime, session: Session = Depends(get_session)
):
    """Read entities."""
    entities = get_entities(start_at, end_at, session)
    return entities


@entity_router.get(
    "/csv/{start_at}/{end_at}/entities.csv",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
)
def read_entities_csv(
    start_at: datetime, end_at: datetime, session: Session = Depends(get_session)
):
    """Download entities csv."""
    entities = get_entities(start_at, end_at, session)

    csv_file = StringIO()
    writer = csv.DictWriter(csv_file, fieldnames=Entity.__fields__.keys())
    writer.writeheader()

    for entity in entities:
        writer.writerow(entity.dict())

    dt_frmt = "%m-%d-%Y_%H-%M-%S"
    start_at_frmt = start_at.strftime(dt_frmt)
    end_at_frmt = end_at.strftime(dt_frmt)

    filename = f"{start_at_frmt}__{end_at_frmt}_entities.csv"

    return StreamingResponse(
        BytesIO(csv_file.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
