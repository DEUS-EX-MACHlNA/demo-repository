"""rename_world_state_to_meta_data

Revision ID: 988e2df6c947
Revises: dc3e5fc3a012
Create Date: 2026-02-09 16:38:53.105618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '988e2df6c947'
down_revision: Union[str, Sequence[str], None] = 'dc3e5fc3a012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('games', 'world_state_data', new_column_name='world_meta_data')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('games', 'world_meta_data', new_column_name='world_state_data')
