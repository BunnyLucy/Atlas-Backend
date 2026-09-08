"""Add versioned world maps.

Revision ID: 20260909_0005
Revises: 20260909_0004
"""
from typing import Sequence, Union

from alembic import op

from atlas_api import models

revision: str = "20260909_0005"
down_revision: Union[str, Sequence[str], None] = "20260909_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    models.WorldMap.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    models.WorldMap.__table__.drop(bind=op.get_bind(), checkfirst=True)
