from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0003"
down_revision: str | None = "20260428_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 4 verification tables and enum values."""
    op.execute("ALTER TYPE candidate_status ADD VALUE IF NOT EXISTS 'verifying'")

    verification_verdict = postgresql.ENUM(
        "pirate",
        "clean",
        "inconclusive",
        name="verification_verdict",
    )
    verification_verdict.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "verification_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audio_score", sa.Float(), nullable=False),
        sa.Column("visual_score", sa.Float(), nullable=False),
        sa.Column("combined_score", sa.Float(), nullable=False),
        sa.Column("gemini_is_sports", sa.Boolean(), nullable=True),
        sa.Column("gemini_detected_sport", sa.String(length=128), nullable=True),
        sa.Column(
            "gemini_broadcaster_logos", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("gemini_confidence", sa.Float(), nullable=True),
        sa.Column(
            "verdict",
            postgresql.ENUM(
                "pirate",
                "clean",
                "inconclusive",
                name="verification_verdict",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("evidence_artifact_id", sa.String(length=255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate_streams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_index(
        "ix_verification_results_match_verdict_verified",
        "verification_results",
        ["match_id", "verdict", "verified_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verification_results_verdict"),
        "verification_results",
        ["verdict"],
        unique=False,
    )

    op.create_table(
        "verification_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "original_verdict",
            postgresql.ENUM(
                "pirate",
                "clean",
                "inconclusive",
                name="verification_verdict",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "override_verdict",
            postgresql.ENUM(
                "pirate",
                "clean",
                "inconclusive",
                name="verification_verdict",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("overridden_by", sa.String(length=255), nullable=False),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["verification_id"], ["verification_results.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verification_overrides_verification_id"),
        "verification_overrides",
        ["verification_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop Phase 4 verification tables and remove enum value."""
    op.drop_index(
        op.f("ix_verification_overrides_verification_id"), table_name="verification_overrides"
    )
    op.drop_table("verification_overrides")
    op.drop_index(op.f("ix_verification_results_verdict"), table_name="verification_results")
    op.drop_index(
        "ix_verification_results_match_verdict_verified", table_name="verification_results"
    )
    op.drop_table("verification_results")
    sa.Enum(name="verification_verdict").drop(op.get_bind(), checkfirst=True)

    op.execute(
        "CREATE TYPE candidate_status_old AS ENUM ('discovered', 'queued_for_verification', 'verified_pirate', 'verified_clean', 'verification_failed')"
    )
    op.execute(
        "ALTER TABLE candidate_streams ALTER COLUMN status TYPE candidate_status_old "
        "USING status::text::candidate_status_old"
    )
    op.execute("DROP TYPE candidate_status")
    op.execute("ALTER TYPE candidate_status_old RENAME TO candidate_status")
