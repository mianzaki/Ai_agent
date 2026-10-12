"""Add organization-scoped Kokoro voice preferences."""

from alembic import op
from sqlalchemy import Column, Float, ForeignKey, String, UniqueConstraint, Uuid

revision = "0002_voice_settings"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_settings",
        Column("id", Uuid, primary_key=True),
        Column("organization_id", Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        Column("agent_id", Uuid, nullable=True),
        Column("voice_id", String(64), nullable=False),
        Column("language", String(16), nullable=False),
        Column("speed", Float, nullable=False),
        UniqueConstraint("organization_id", "agent_id", name="uq_voice_setting_org_agent"),
    )
    op.create_index("ix_voice_settings_organization_id", "voice_settings", ["organization_id"])


def downgrade() -> None:
    op.drop_table("voice_settings")
