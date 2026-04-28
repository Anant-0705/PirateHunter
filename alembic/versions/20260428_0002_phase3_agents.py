from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0002"
down_revision: str | None = "20260428_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 3 discovery agent tables."""
    candidate_status = postgresql.ENUM(
        "discovered",
        "queued_for_verification",
        "verified_pirate",
        "verified_clean",
        "verification_failed",
        name="candidate_status",
    )
    candidate_status.create(op.get_bind(), checkfirst=True)

    agent_run_status = postgresql.ENUM(
        "running",
        "succeeded",
        "failed",
        name="agent_run_status",
    )
    agent_run_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "candidate_streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_platform", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discovered_by_agent", sa.String(length=128), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_hint", sa.Float(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "discovered",
                "queued_for_verification",
                "verified_pirate",
                "verified_clean",
                "verification_failed",
                name="candidate_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "source_url", name="uq_candidate_streams_match_source_url"),
    )
    op.create_index(
        "ix_candidate_streams_source_url",
        "candidate_streams",
        ["source_url"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_streams_status"),
        "candidate_streams",
        ["status"],
        unique=False,
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "running",
                "succeeded",
                "failed",
                name="agent_run_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("candidates_found", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_agent_name"), "agent_runs", ["agent_name"], unique=False)
    op.create_index(op.f("ix_agent_runs_status"), "agent_runs", ["status"], unique=False)


def downgrade() -> None:
    """Drop Phase 3 discovery agent tables."""
    op.drop_index(op.f("ix_agent_runs_status"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_agent_name"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_candidate_streams_status"), table_name="candidate_streams")
    op.drop_index("ix_candidate_streams_source_url", table_name="candidate_streams")
    op.drop_table("candidate_streams")
    sa.Enum(name="agent_run_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="candidate_status").drop(op.get_bind(), checkfirst=True)
