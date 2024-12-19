"""Config module."""

from pydantic import BaseSettings


class Settings(BaseSettings):
    """Settings."""

    # Base
    api_v1_prefix: str
    debug: bool
    project_name: str
    version: str
    description: str

    # Kafka
    kafka_client_id: str
    kafka_bootstrap_servers: str
    kafka_topic: str
