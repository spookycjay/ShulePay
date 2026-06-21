"""Add schools table and school_id to all tables

Revision ID: a47f57f6105f
Revises: c4668fec05dd
Create Date: 2026-06-21 03:30:39.142400

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a47f57f6105f'
down_revision = 'c4668fec05dd'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1 - Create schools table first
    op.create_table('schools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('address', sa.String(length=255), nullable=True),
        sa.Column('logo', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    # Step 2 - Insert a default school for existing data
    op.execute("""
        INSERT INTO schools (id, name, email, phone, address, is_active, created_at)
        VALUES (1, 'Default School', 'admin@school.com', '0700000000', 'Nairobi, Kenya', 1, NOW())
    """)

    # Step 3 - Add school_id columns as NULLABLE first
    op.add_column('classes', sa.Column('school_id', sa.Integer(), nullable=True))
    op.add_column('fee_structures', sa.Column('school_id', sa.Integer(), nullable=True))
    op.add_column('parents', sa.Column('school_id', sa.Integer(), nullable=True))
    op.add_column('payments', sa.Column('school_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('school_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('school_id', sa.Integer(), nullable=True))

    # Step 4 - Assign all existing data to the default school
    op.execute("UPDATE classes SET school_id = 1 WHERE school_id IS NULL")
    op.execute("UPDATE fee_structures SET school_id = 1 WHERE school_id IS NULL")
    op.execute("UPDATE parents SET school_id = 1 WHERE school_id IS NULL")
    op.execute("UPDATE payments SET school_id = 1 WHERE school_id IS NULL")
    op.execute("UPDATE students SET school_id = 1 WHERE school_id IS NULL")
    op.execute("UPDATE users SET school_id = 1 WHERE school_id IS NULL")

    # Step 5 - Remove old unique index on classes.name
    op.drop_index('name', table_name='classes')

    # Step 6 - Remove class_name column from students
    op.drop_column('students', 'class_name')

    # Step 7 - Add foreign key constraints
    op.create_foreign_key(None, 'classes', 'schools', ['school_id'], ['id'])
    op.create_foreign_key(None, 'fee_structures', 'schools', ['school_id'], ['id'])
    op.create_foreign_key(None, 'parents', 'schools', ['school_id'], ['id'])
    op.create_foreign_key(None, 'payments', 'schools', ['school_id'], ['id'])
    op.create_foreign_key(None, 'students', 'schools', ['school_id'], ['id'])
    op.create_foreign_key(None, 'users', 'schools', ['school_id'], ['id'])


def downgrade():
    # Remove foreign keys
    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_constraint(None, 'students', type_='foreignkey')
    op.drop_constraint(None, 'payments', type_='foreignkey')
    op.drop_constraint(None, 'parents', type_='foreignkey')
    op.drop_constraint(None, 'fee_structures', type_='foreignkey')
    op.drop_constraint(None, 'classes', type_='foreignkey')

    # Remove school_id columns
    op.drop_column('users', 'school_id')
    op.drop_column('students', 'school_id')
    op.drop_column('payments', 'school_id')
    op.drop_column('parents', 'school_id')
    op.drop_column('fee_structures', 'school_id')
    op.drop_column('classes', 'school_id')

    # Restore unique index on classes.name
    op.create_index('name', 'classes', ['name'], unique=True)

    # Drop schools table
    op.drop_table('schools')