"""merge event ingestion and describe change heads

Revision ID: 82150c096aae
Revises: 20260823_0002, 876befa85d63
Create Date: 2026-08-27 16:11:51.431877
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '82150c096aae'
down_revision: Union[str, None] = ('20260823_0002', '876befa85d63')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
