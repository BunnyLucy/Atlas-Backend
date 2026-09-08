"""Add collaboration workflow tables.

Revision ID: 20260909_0003
Revises: 20260909_0002
"""
from typing import Sequence, Union
from alembic import op
from atlas_api import models

revision: str = "20260909_0003"
down_revision: Union[str, Sequence[str], None] = "20260909_0002"
branch_labels = None
depends_on = None


TABLES = [
    models.CharacterProfile.__table__, models.WorldTask.__table__, models.TaskParticipant.__table__,
    models.Submission.__table__, models.SubmissionConfirmation.__table__, models.SubmissionReview.__table__,
    models.ContributionEvent.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind=bind, checkfirst=True)
