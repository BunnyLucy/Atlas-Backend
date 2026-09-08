"""Add complete membership workflows.

Revision ID: 20260909_0002
Revises: 20260909_0001
"""
from typing import Sequence, Union

from alembic import op

from atlas_api import models

revision: str = "20260909_0002"
down_revision: Union[str, Sequence[str], None] = "20260909_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    models.WorldInvitation.__table__.create(bind=bind, checkfirst=True)
    models.WorldJoinRequest.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    models.WorldJoinRequest.__table__.drop(bind=bind, checkfirst=True)
    models.WorldInvitation.__table__.drop(bind=bind, checkfirst=True)
