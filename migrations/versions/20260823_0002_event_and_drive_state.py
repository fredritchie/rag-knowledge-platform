"""Add durable S3 event receipts and Google Drive checkpoints.

Revision ID: 20260823_0002
Revises: 20260823_0001
"""

from alembic import op

from rag_platform.application.db.models import DriveChangeEvent, DriveCheckpoint, IngestionReceipt

revision = "20260823_0002"
down_revision = "20260823_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    IngestionReceipt.__table__.create(bind=bind, checkfirst=True)
    DriveCheckpoint.__table__.create(bind=bind, checkfirst=True)
    DriveChangeEvent.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    DriveChangeEvent.__table__.drop(bind=bind, checkfirst=True)
    DriveCheckpoint.__table__.drop(bind=bind, checkfirst=True)
    IngestionReceipt.__table__.drop(bind=bind, checkfirst=True)
