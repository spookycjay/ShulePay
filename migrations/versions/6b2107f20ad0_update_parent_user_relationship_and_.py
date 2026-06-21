"""Update parent-user relationship and payment fields

Revision ID: 6b2107f20ad0
Revises: 
Create Date: 2026-06-09 21:00:02.823035
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '6b2107f20ad0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('classes', schema=None) as batch_op:
        batch_op.create_unique_constraint(None, ['name'])

    with op.batch_alter_table('parents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.alter_column(
            'email',
            existing_type=mysql.VARCHAR(length=150),
            nullable=False
        )
        batch_op.create_unique_constraint(None, ['email'])
        batch_op.create_unique_constraint(None, ['user_id'])
        batch_op.create_foreign_key(None, 'users', ['user_id'], ['id'])

    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('payment_method', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('status', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('status')
        batch_op.drop_column('payment_method')
        batch_op.drop_column('created_at')

    with op.batch_alter_table('parents', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_constraint(None, type_='unique')
        batch_op.alter_column(
            'email',
            existing_type=mysql.VARCHAR(length=150),
            nullable=True
        )
        batch_op.drop_column('user_id')

    with op.batch_alter_table('classes', schema=None) as batch_op:
        batch_op.drop_constraint(None, type_='unique')