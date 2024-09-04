"""CRUD module."""

from datetime import datetime
from typing import List
from uuid import UUID

from sqlmodel import Session

from app.models import Entity


def get_entity(uid: str | UUID, session: Session) -> Entity:
    """Read entity."""
    return session.query(Entity).filter(Entity.uid == uid).first()


def get_entities(
    start_at: datetime, end_at: datetime, session: Session
) -> List[Entity]:
    """Read entities."""
    period = Entity.ts.between(str(start_at), str(end_at))
    entities = session.query(Entity).filter(period).all()
    return entities


def post_entity(entity: Entity, session: Session) -> Entity:
    """Create entity."""
    session.add(entity)
    session.commit()
    session.refresh(entity)
    return entity
