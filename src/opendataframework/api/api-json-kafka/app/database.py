"""Database module."""

import asyncio

from aiokafka import AIOKafkaProducer

from app import settings

loop = asyncio.get_event_loop()

kafka_producer = AIOKafkaProducer(
    loop=loop,
    client_id=settings.kafka_client_id,
    bootstrap_servers=settings.kafka_bootstrap_servers,
)
