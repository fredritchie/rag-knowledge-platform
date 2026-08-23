"""Create Phase 5-8 application schema.

Revision ID: 20260823_0001
Revises: None
"""
from alembic import op

from rag_platform.application.db.models import Base

revision = "20260823_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
