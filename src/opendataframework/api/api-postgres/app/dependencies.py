"""Dependencies module."""

from sqlmodel import Session

from app.database import engine


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session
