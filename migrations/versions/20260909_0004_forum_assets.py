"""Add forums and versioned assets.

Revision ID: 20260909_0004
Revises: 20260909_0003
"""
from typing import Sequence, Union

from alembic import op

from atlas_api import models

revision: str = "20260909_0004"
down_revision: Union[str, Sequence[str], None] = "20260909_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in (models.ForumSpace, models.ForumTopic, models.ForumPost, models.Asset, models.PendingUpload, models.AssetVersion, models.AssetReference):
        table.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in (models.AssetReference, models.AssetVersion, models.PendingUpload, models.Asset, models.ForumPost, models.ForumTopic, models.ForumSpace):
        table.__table__.drop(bind=bind, checkfirst=True)
