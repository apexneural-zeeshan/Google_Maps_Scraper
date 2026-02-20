"""no-op alignment revision

Revision ID: b4b4d9c00244
Revises: 68d84006fdb1
Create Date: 2026-02-17 15:59:00.111734

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4b4d9c00244'
down_revision: Union[str, None] = '68d84006fdb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally empty: this revision was generated during development
    # and kept in the chain to preserve Alembic history consistency.
    return None


def downgrade() -> None:
    # Intentionally empty for the same reason as upgrade().
    return None
