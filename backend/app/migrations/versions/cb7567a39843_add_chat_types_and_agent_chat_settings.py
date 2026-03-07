"""add_chat_types_and_agent_chat_settings

Revision ID: cb7567a39843
Revises: e876d71bda23
Create Date: 2026-03-06 21:30:26.238208
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'cb7567a39843'
down_revision: Union[str, None] = 'e876d71bda23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add chat_type, project_slug, task_id, unread_count to chat_sessions
    op.add_column('chat_sessions', sa.Column('chat_type', sa.String(20), nullable=False, server_default='user'))
    op.add_column('chat_sessions', sa.Column('project_slug', sa.String(200), nullable=True))
    op.add_column('chat_sessions', sa.Column('task_id', sa.String(100), nullable=True))
    op.add_column('chat_sessions', sa.Column('unread_count', sa.Integer(), nullable=False, server_default='0'))
    
    # Add max_messages_before_response to agents
    op.add_column('agents', sa.Column('max_messages_before_response', sa.Integer(), nullable=False, server_default='5'))


def downgrade() -> None:
    # Remove columns from chat_sessions
    op.drop_column('chat_sessions', 'unread_count')
    op.drop_column('chat_sessions', 'task_id')
    op.drop_column('chat_sessions', 'project_slug')
    op.drop_column('chat_sessions', 'chat_type')
    
    # Remove column from agents
    op.drop_column('agents', 'max_messages_before_response')
