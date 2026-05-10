"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- sources ---
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500)),
        sa.Column("full_text", sa.Text),
        sa.Column("source_type", sa.String(50)),
        sa.Column("file_path", sa.String(1000)),
        sa.Column("url", sa.String(2000)),
        sa.Column("minio_key", sa.String(500)),
        sa.Column("file_name", sa.String(500)),
        sa.Column("file_size", sa.Integer),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("error_message", sa.Text),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- source_chunks ---
    op.create_table(
        "source_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(768)),
        sa.Column("chunk_index", sa.Integer, server_default="0"),
        sa.Column("page_number", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_source_chunks_source_id", "source_chunks", ["source_id"])

    # HNSW index for vector search
    op.execute("""
        CREATE INDEX ix_source_chunks_embedding_hnsw
        ON source_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # --- source_insights ---
    op.create_table(
        "source_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("insight_type", sa.String(100)),
        sa.Column("content", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- chunk_images ---
    op.create_table(
        "chunk_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("source_chunks.id", ondelete="CASCADE")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("minio_key", sa.String(500), nullable=False),
        sa.Column("caption", sa.Text),
        sa.Column("page_number", sa.Integer),
        sa.Column("image_index", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chunk_images_chunk_id", "chunk_images", ["chunk_id"])
    op.create_index("ix_chunk_images_source_id", "chunk_images", ["source_id"])

    # --- notes ---
    op.create_table(
        "notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text),
        sa.Column("note_type", sa.String(50)),
        sa.Column("embedding", Vector(768)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- contacts ---
    op.create_table(
        "contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(200)),
        sa.Column("phone", sa.String(50)),
        sa.Column("email", sa.String(200)),
        sa.Column("topics", ARRAY(sa.String)),
        sa.Column("note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- channel_users ---
    op.create_table(
        "channel_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_type", sa.String(50), nullable=False),
        sa.Column("channel_user_id", sa.String(200), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("avatar_url", sa.String(500)),
        sa.Column("last_active", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_channel_users_unique", "channel_users",
        ["channel_type", "channel_user_id"], unique=True,
    )

    # --- chat_sessions ---
    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("channel_user_id", UUID(as_uuid=True), sa.ForeignKey("channel_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("last_active", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- chat_messages ---
    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("image_urls", JSONB),
        sa.Column("source_refs", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # --- app_config ---
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("channel_users")
    op.drop_table("contacts")
    op.drop_table("notes")
    op.drop_table("chunk_images")
    op.drop_table("source_insights")
    op.drop_table("source_chunks")
    op.drop_table("sources")
    op.execute("DROP EXTENSION IF EXISTS vector")
