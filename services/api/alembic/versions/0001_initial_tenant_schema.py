"""Initial organization, user, agent, session and event schema."""

from alembic import op
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        Column("id", Uuid, primary_key=True),
        Column("name", String(200), nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    op.create_table(
        "users",
        Column("id", Uuid, primary_key=True),
        Column("auth_subject", String(255), nullable=False),
        Column("email", String(320)),
        Column("active", Boolean, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        UniqueConstraint("auth_subject", name="uq_users_auth_subject"),
        UniqueConstraint("id", "auth_subject", name="uq_users_id_auth_subject"),
    )
    op.create_table(
        "memberships",
        Column("id", Uuid, primary_key=True),
        Column(
            "organization_id",
            Uuid,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("user_id", Uuid, nullable=False),
        Column("auth_subject", String(255), nullable=False),
        Column("role", String(32), nullable=False),
        Column("active", Boolean, nullable=False),
        UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),
        CheckConstraint(
            "role IN ('owner', 'admin', 'operator', 'viewer')", name="ck_membership_role"
        ),
        ForeignKeyConstraint(
            ["user_id", "auth_subject"],
            ["users.id", "users.auth_subject"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_memberships_organization_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "agents",
        Column("id", Uuid, primary_key=True),
        Column(
            "organization_id",
            Uuid,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("name", String(200), nullable=False),
        Column("instructions", Text, nullable=False),
        Column("config", JSON, nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        UniqueConstraint("id", "organization_id", name="uq_agents_id_organization_id"),
    )
    op.create_index("ix_agents_organization_id", "agents", ["organization_id"])
    op.create_table(
        "sessions",
        Column("id", Uuid, primary_key=True),
        Column(
            "organization_id",
            Uuid,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("agent_id", Uuid, nullable=False),
        Column("status", String(32), nullable=False),
        Column("started_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        Column("ended_at", DateTime(timezone=True)),
        UniqueConstraint("id", "organization_id", name="uq_sessions_id_organization_id"),
        ForeignKeyConstraint(
            ["organization_id", "agent_id"],
            ["agents.organization_id", "agents.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_sessions_organization_id", "sessions", ["organization_id"])
    op.create_table(
        "events",
        Column("id", Uuid, primary_key=True),
        Column(
            "organization_id",
            Uuid,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("session_id", Uuid, nullable=False),
        Column("sequence", Integer, nullable=False),
        Column("kind", String(64), nullable=False),
        Column("payload", JSON, nullable=False),
        Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        ForeignKeyConstraint(
            ["organization_id", "session_id"],
            ["sessions.organization_id", "sessions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "session_id", "sequence", name="uq_event_session_sequence"
        ),
    )
    op.create_index("ix_events_organization_id", "events", ["organization_id"])
    op.create_index("ix_events_session_id", "events", ["session_id"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("sessions")
    op.drop_table("agents")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("organizations")
