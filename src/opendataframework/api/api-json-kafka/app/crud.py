"""CRUD module."""

import json

from fastapi.encoders import jsonable_encoder

from app import settings
from app.database import kafka_producer
from app.models import Entity


async def post_entity(entity: Entity) -> Entity:
    """Create entity."""
    data = json.dumps(jsonable_encoder(entity)).encode("ascii")
    await kafka_producer.send(settings.kafka_topic, data)
    return entity
