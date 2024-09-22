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
