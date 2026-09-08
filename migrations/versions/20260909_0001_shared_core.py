"""Create the Atlas shared core schema.

Revision ID: 20260909_0001
Revises:
"""
from typing import Sequence, Union

from alembic import op

from atlas_api import models  # noqa: F401
from atlas_api.db import Base

revision: str = "20260909_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)

