from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260428_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 2 persistence tables."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    match_status = postgresql.ENUM(
        "pending",
        "ingesting",
        "ready",
        "failed",
        name="match_status",
    )
    match_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "ingesting",
                "ready",
                "failed",
                name="match_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_matches_status"), "matches", ["status"], unique=False)

    op.create_table(
        "audio_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("chromaprint_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("fallback_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audio_fingerprints_match_chunk",
        "audio_fingerprints",
        ["match_id", "chunk_index"],
        unique=False,
    )

    op.create_table(
        "visual_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("phash", sa.String(length=16), nullable=False),
        sa.Column("dhash", sa.String(length=16), nullable=False),
        sa.Column("phash_vector", pgvector.sqlalchemy.Vector(dim=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_visual_fingerprints_match_frame",
        "visual_fingerprints",
        ["match_id", "frame_index"],
        unique=False,
    )
    op.create_index(
        "ix_visual_fingerprints_phash_vector_hnsw",
        "visual_fingerprints",
        ["phash_vector"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"phash_vector": "vector_l2_ops"},
    )


def downgrade() -> None:
    """Drop Phase 2 persistence tables."""
    op.drop_index("ix_visual_fingerprints_phash_vector_hnsw", table_name="visual_fingerprints")
    op.drop_index("ix_visual_fingerprints_match_frame", table_name="visual_fingerprints")
    op.drop_table("visual_fingerprints")
    op.drop_index("ix_audio_fingerprints_match_chunk", table_name="audio_fingerprints")
    op.drop_table("audio_fingerprints")
    op.drop_index(op.f("ix_matches_status"), table_name="matches")
    op.drop_table("matches")
    sa.Enum(name="match_status").drop(op.get_bind(), checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS vector")
