"""Add local users, sessions, selections, and learned preferences.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "profile_id",
            sa.String(128),
            sa.ForeignKey("preference_profiles.profile_id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])
    op.create_table(
        "learned_preference_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("learning_enabled", sa.Boolean(), nullable=False),
        sa.Column("quiet_priority", sa.Float()),
        sa.Column("low_occupancy_priority", sa.Float()),
        sa.Column("brightness_priority", sa.Float()),
        sa.Column("comfort_priority", sa.Float()),
        sa.Column("quiet_evidence_count", sa.Integer(), nullable=False),
        sa.Column("low_occupancy_evidence_count", sa.Integer(), nullable=False),
        sa.Column("brightness_evidence_count", sa.Integer(), nullable=False),
        sa.Column("comfort_evidence_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "room_selection_events",
        sa.Column("selection_id", sa.String(36), primary_key=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("room_id", sa.String(128), sa.ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_request_id", sa.String(128)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_rank", sa.Integer()),
        sa.Column("selected_score", sa.Integer()),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("context_summary_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_room_selection_events_room_id", "room_selection_events", ["room_id"])
    op.create_index("ix_room_selection_events_recorded_at", "room_selection_events", ["recorded_at"])
    op.create_index(
        "ix_room_selection_events_user_recorded",
        "room_selection_events",
        ["user_id", "recorded_at"],
    )
    with op.batch_alter_table("recommendation_records") as batch:
        batch.add_column(sa.Column("user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("score_breakdown_json", sa.JSON(), nullable=True))
        batch.create_foreign_key(
            "fk_recommendation_records_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_recommendation_records_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("recommendation_records") as batch:
        batch.drop_index("ix_recommendation_records_user_id")
        batch.drop_constraint("fk_recommendation_records_user_id_users", type_="foreignkey")
        batch.drop_column("score_breakdown_json")
        batch.drop_column("user_id")
    op.drop_table("room_selection_events")
    op.drop_table("learned_preference_profiles")
    op.drop_table("user_sessions")
    op.drop_table("users")
