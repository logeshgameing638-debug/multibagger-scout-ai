"""Initial schema: create all tables."""
from database.models import Base


def upgrade(engine) -> None:
    Base.metadata.create_all(engine)
