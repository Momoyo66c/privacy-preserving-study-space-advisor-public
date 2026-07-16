"""Create module 3 tables.

Revision ID: 0001
Revises:
"""
from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("location", sa.String(300)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("capacity_band", sa.String(16)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rooms_active", "rooms", ["active"])
    op.create_table(
        "devices",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("room_id", sa.String(128), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("firmware_version", sa.String(100)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_devices_room_id", "devices", ["room_id"])
    op.create_table(
        "observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("observation_id", sa.String(128), nullable=False, unique=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("room_id", sa.String(128), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("device_id", sa.String(128), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("room_state", sa.String(64), nullable=False),
        sa.Column("occupancy_level", sa.String(16), nullable=False),
        sa.Column("suitability_score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("feature_summary_json", sa.JSON(), nullable=False),
        sa.Column("sensor_health_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("feature_schema_version", sa.String(100), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_observations_room_observed", "observations", ["room_id", "observed_at"])
    op.create_index("ix_observations_synthetic", "observations", ["synthetic"])
    op.create_table(
        "preference_profiles",
        sa.Column("profile_id", sa.String(128), primary_key=True),
        sa.Column("study_mode", sa.String(16), nullable=False),
        sa.Column("quiet_priority", sa.Float(), nullable=False),
        sa.Column("low_occupancy_priority", sa.Float(), nullable=False),
        sa.Column("brightness_priority", sa.Float(), nullable=False),
        sa.Column("comfort_priority", sa.Float(), nullable=False),
        sa.Column("distance_priority", sa.Float(), nullable=False),
        sa.Column("preferred_temperature_c", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.String(128), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False),
        sa.Column("predicted_occupancy_level", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("input_start_at", sa.DateTime(timezone=True)),
        sa.Column("input_end_at", sa.DateTime(timezone=True)),
        sa.Column("fallback_reason", sa.String(128)),
    )
    op.create_index("ix_forecasts_room_target", "forecasts", ["room_id", "target_at"])
    op.create_index("ix_forecasts_room_horizon_generated", "forecasts", ["room_id", "horizon_minutes", "generated_at"])
    op.create_table(
        "recommendation_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(128), nullable=False, unique=True),
        sa.Column("profile_id", sa.String(128), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("candidate_room_ids_json", sa.JSON(), nullable=False),
        sa.Column("rankings_json", sa.JSON(), nullable=False),
        sa.Column("explanation_source", sa.String(32), nullable=False),
        sa.Column("adapter_name", sa.String(100), nullable=False),
        sa.Column("fallback_reason", sa.String(200)),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_recommendation_records_profile_id", "recommendation_records", ["profile_id"])
    op.create_index("ix_recommendation_records_generated_at", "recommendation_records", ["generated_at"])


def downgrade() -> None:
    op.drop_table("recommendation_records")
    op.drop_table("forecasts")
    op.drop_table("preference_profiles")
    op.drop_table("observations")
    op.drop_table("devices")
    op.drop_table("rooms")
