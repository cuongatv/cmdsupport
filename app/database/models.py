"""
SQLAlchemy ORM models for all database tables.

Permission Architecture v2 — Dual-Realm:
  - Global Realm: scoped permissions (doc:read:own_dept, doc:read:all, etc.)
  - Workspace Realm: membership-gated (viewer / contributor / editor / admin)
"""

import uuid
from datetime import date, datetime, time
from enum import Enum as PyEnum
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScopeType(str, PyEnum):
    """Scope for sources/wiki: global or project (workspace).
    Department visibility is handled via source_departments M2M.
    """

    GLOBAL = "global"
    PROJECT = "project"


class WorkspaceRole(str, PyEnum):
    """Role within a workspace (ordered by privilege level)."""

    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    EDITOR = "editor"
    ADMIN = "admin"


class UnitType(str, PyEnum):
    BUSINESS_GROUP = "business_group"
    SQUAD_TEAM = "squad_team"


class MembershipRole(str, PyEnum):
    LEAD = "lead"
    DEPUTY_LEAD = "deputy_lead"
    CONTROLLER = "controller"
    MEMBER = "member"
    PRODUCT_OWNER = "product_owner"
    SCRUM_MASTER = "scrum_master"
    DEVELOPER = "developer"


class TaskPriority(str, PyEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class HabitOccurrenceStatus(str, PyEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SHIFTED = "shifted"


WORKSPACE_ROLE_HIERARCHY: dict[WorkspaceRole, int] = {
    WorkspaceRole.VIEWER: 0,
    WorkspaceRole.CONTRIBUTOR: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.ADMIN: 3,
}


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# ---------------------------------------------------------------------------
# Sources — raw documents (file/URL)
# ---------------------------------------------------------------------------


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[Optional[str]] = mapped_column(String(500))
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    source_type: Mapped[Optional[str]] = mapped_column(String(50))  # "file", "url"
    # --- Scope: global or project (workspace) ---
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default=ScopeType.GLOBAL.value,
        comment="Scope type: global or project",
    )
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Project/workspace ID when scope_type=project. Null for global.",
    )
    knowledge_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    contributed_by_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(1000))
    url: Mapped[Optional[str]] = mapped_column(String(2000))
    minio_key: Mapped[Optional[str]] = mapped_column(String(500))
    file_name: Mapped[Optional[str]] = mapped_column(String(500))
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[Optional[str]] = mapped_column(String(500))
    job_id: Mapped[Optional[str]] = mapped_column(String(200))
    pipeline_strategy: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="MRP triage strategy for opt-in ingestion, e.g. map_reduce or refine",
    )
    pipeline_phase: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Current MRP pipeline phase for opt-in ingestion",
    )
    # Heading-based TOC tree (PageIndex-style) built at ingest time from extracted markdown.
    # Schema: [{"title": str, "level": int, "page": int, "char_start": int, "char_end": int, "children": [...]}]
    outline_json: Mapped[Optional[list]] = mapped_column(JSONB)
    # Char offset (in full_text) where each extracted page begins.
    # Used by MCP `get_source_pages` to slice raw text by page range.
    page_offsets: Mapped[Optional[list[int]]] = mapped_column(JSONB)
    pipeline_strategy: Mapped[Optional[str]] = mapped_column(
        String(20),
        comment="MRP strategy: single_pass | standard | hierarchical",
    )
    pipeline_phase: Mapped[Optional[str]] = mapped_column(
        String(30),
        comment="Current MRP phase: map | reduce | plan_review | refine | verify | commit",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    departments: Mapped[list["SourceDepartment"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    knowledge_type: Mapped[Optional["KnowledgeType"]] = relationship()
    contributor: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[contributed_by_employee_id]
    )
    mrp_plan: Mapped[Optional["MRPPlan"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
        uselist=False,
    )
    mrp_artifacts: Mapped[list["MRPArtifact"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )


class MRPPlan(Base):
    """Human-reviewable plan produced by the opt-in map/reduce pipeline."""

    __tablename__ = "mrp_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    strategy: Mapped[str] = mapped_column(
        String(50), nullable=False, default="map_reduce"
    )
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="mrp_plan")
    approved_by: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[approved_by_id]
    )
    rejected_by: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[rejected_by_id]
    )

    __table_args__ = (
        Index("ix_mrp_plans_source_id", "source_id"),
        Index("ix_mrp_plans_status", "status"),
    )


class MRPArtifact(Base):
    """Intermediate artifact from MRP map/reduce/refine/commit phases."""

    __tablename__ = "mrp_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="mrp_artifacts")

    __table_args__ = (
        Index("ix_mrp_artifacts_source_phase", "source_id", "phase"),
        Index("ix_mrp_artifacts_source_type", "source_id", "artifact_type"),
    )


class SourceDepartment(Base):
    """Many-to-many: Source ↔ Department.
    A source with NO rows here is considered Global (visible to all).
    """

    __tablename__ = "source_departments"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="departments")
    department: Mapped["Department"] = relationship(back_populates="source_departments")


class SourceChunkExtract(Base):
    """Persisted Phase 1 MAP output for one source chunk."""

    __tablename__ = "source_chunk_extracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[Optional[str]] = mapped_column(Text)
    extract_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["Source"] = relationship()

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_sce_source_chunk"),
        Index("ix_sce_source_status", "source_id", "status"),
    )


class SourceCompilationPlan(Base):
    """Persisted Phase 2 REDUCE plan awaiting human review or approval.

    Statuses:
      - pending_review: chờ user duyệt
      - revising: đang regenerate theo feedback (lock chống click đôi)
      - approved: đã duyệt, refine đang chạy hoặc đã chạy
      - rejected: bị từ chối (không tái sinh)
    """

    __tablename__ = "source_compilation_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    plan_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_review"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    review_note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    source: Mapped["Source"] = relationship()
    reviewer: Mapped[Optional["Employee"]] = relationship(foreign_keys=[reviewed_by])
    revisions: Mapped[list["SourceCompilationPlanRevision"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="SourceCompilationPlanRevision.created_at.desc()",
    )

    __table_args__ = (Index("ix_scp_status", "status"),)


class SourceCompilationPlanRevision(Base):
    """Lịch sử request-changes của một plan.

    Mỗi lần user yêu cầu chỉnh sửa sẽ tạo 1 row mới, lưu feedback và snapshot
    plan trước khi regenerate. Status chuyển từ ``requested`` → ``running`` →
    ``succeeded`` / ``failed``.
    """

    __tablename__ = "source_compilation_plan_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_compilation_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_plan_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    plan: Mapped["SourceCompilationPlan"] = relationship(back_populates="revisions")
    requester: Mapped[Optional["Employee"]] = relationship(foreign_keys=[requested_by])

    __table_args__ = (
        Index("ix_scp_revision_plan", "plan_id"),
        Index("ix_scp_revision_source_status", "source_id", "status"),
    )


# ---------------------------------------------------------------------------
# Wiki — LLM-compiled persistent knowledge layer
# ---------------------------------------------------------------------------


class WikiPage(Base):
    """
    A markdown wiki page maintained by the LLM Wiki Compiler.
    Reserved slugs: '_index' (catalog), '_log' (chronological activity log).
    """

    __tablename__ = "wiki_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # --- Scope: global or project (workspace) ---
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default=ScopeType.GLOBAL.value,
        comment="Scope type: global or project",
    )
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Project/workspace ID. Null for global scope.",
    )
    knowledge_type_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    source_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    embedding = mapped_column(Vector(768), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    orphaned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_wiki_pages_page_type", "page_type"),)


class WikiLink(Base):
    """
    Derived edge between two wiki pages, parsed from `[[slug]]` patterns in content_md.
    Refreshed after every page upsert by wiki_service.refresh_links().
    """

    __tablename__ = "wiki_links"

    from_slug: Mapped[str] = mapped_column(String(300), nullable=False)
    to_slug: Mapped[str] = mapped_column(String(300), nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("from_slug", "to_slug"),
        Index("ix_wiki_links_from_slug", "from_slug"),
        Index("ix_wiki_links_to_slug", "to_slug"),
    )


class WikiPageDraft(Base):
    """
    Pending contribution proposed by a workspace member.
    An editor/admin reviews and either approves (writing to wiki_pages.content_md)
    or rejects (with a reviewer_note explaining why).
    Multiple drafts per page are allowed — editor resolves all.
    """

    __tablename__ = "wiki_page_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # web_ui | mcp_claude_desktop | mcp_claude_code | mcp_other | api_direct
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="web_ui")
    source_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    page: Mapped["WikiPage"] = relationship("WikiPage", foreign_keys=[page_id])
    author: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[author_id]
    )
    reviewer: Mapped[Optional["Employee"]] = relationship(
        "Employee", foreign_keys=[reviewed_by_id]
    )

    __table_args__ = (
        Index("ix_wiki_drafts_page_id", "page_id"),
        Index("ix_wiki_drafts_status", "status"),
        Index("ix_wiki_drafts_author_id", "author_id"),
    )


class WikiPageRevision(Base):
    """
    Immutable snapshot of wiki page content at each version.
    Created on every content-changing operation: agent compile, editor edit,
    draft approval, manual rebuild, rollback.
    """

    __tablename__ = "wiki_page_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    # agent_compile | agent_retry | editor_edit | draft_approved | manual_rebuild | rollback
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    draft_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_page_drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    changed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_wiki_revisions_page_id", "page_id"),
        Index("ix_wiki_revisions_page_version", "page_id", "version"),
    )


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[Optional[str]] = mapped_column(String(500))
    content: Mapped[Optional[str]] = mapped_column(Text)
    note_type: Mapped[Optional[str]] = mapped_column(String(50))  # "human", "ai"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# App Config (key-value store for settings)
# ---------------------------------------------------------------------------


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Knowledge Types (admin-defined, dynamic)
# ---------------------------------------------------------------------------


class KnowledgeType(Base):
    """
    Admin-defined knowledge type — replaces hardcoded types.
    Examples: SOP, Product, HR Policy, Technical Spec, etc.
    """

    __tablename__ = "knowledge_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        comment="URL-safe identifier, e.g. 'sop', 'product', 'hr-policy'",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name, e.g. 'Standard Operating Procedure'",
    )
    color: Mapped[Optional[str]] = mapped_column(
        String(20),
        default="#6366f1",
        comment="Hex color for UI badge",
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# RBAC: Roles, Departments, Employees
# ---------------------------------------------------------------------------


class Role(Base):
    """Custom permission role assignable to employees.
    Permissions use scoped format: resource:action:scope
    e.g. 'doc:read:own_dept', 'doc:read:all', 'org:settings:manage'
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    permissions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    employees: Mapped[list["Employee"]] = relationship(back_populates="custom_role")


class Department(Base):
    """Organizational department — groups employees and scopes knowledge access."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    unit_type: Mapped[UnitType] = mapped_column(
        SQLAlchemyEnum(
            UnitType,
            name="unit_type_enum",
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=UnitType.BUSINESS_GROUP,
        server_default="business_group",
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    employees: Mapped[list["Employee"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["EmployeeDepartmentMembership"]] = relationship(
        "EmployeeDepartmentMembership",
        back_populates="department",
        cascade="all, delete-orphan",
    )
    source_departments: Mapped[list["SourceDepartment"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    skill_departments: Mapped[list["SkillDepartment"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )


class Employee(Base):
    """
    Employee — authenticates via login (JWT) or MCP token.
    Role 'admin' has full access (bypasses all permission checks).
    Role 'employee' access is governed by custom_role permissions.
    """

    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="bcrypt hash of password",
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default="employee",
        comment="admin or employee — system-level role",
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE")
    )
    custom_role_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )
    mcp_token: Mapped[Optional[str]] = mapped_column(
        String(500),
        unique=True,
        comment="Bearer token for MCP authentication",
    )
    phone: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="Primary phone number",
    )
    zalo_phone: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="Zalo phone number; if empty, fall back to `phone` for Zalo tasks",
    )
    avatar_key: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Object storage key for avatar image (jpg/jpeg/png/webp)",
    )
    slogan: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="User-supplied slogan / motto",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_connected: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    department: Mapped["Department"] = relationship(back_populates="employees")
    memberships: Mapped[list["EmployeeDepartmentMembership"]] = relationship(
        "EmployeeDepartmentMembership",
        back_populates="employee",
        foreign_keys="EmployeeDepartmentMembership.employee_id",
        cascade="all, delete-orphan",
    )
    custom_role: Mapped[Optional["Role"]] = relationship(back_populates="employees")
    assigned_provinces: Mapped[list["Province"]] = relationship(
        back_populates="assigned_employee",
        foreign_keys="Province.assigned_employee_id",
    )
    personal_task_projects: Mapped[list["TaskProject"]] = relationship(
        back_populates="owner_employee",
        foreign_keys="TaskProject.owner_employee_id",
    )
    personal_habits: Mapped[list["PersonalHabit"]] = relationship(
        back_populates="owner_employee",
        foreign_keys="PersonalHabit.owner_employee_id",
    )

    __table_args__ = (
        Index("ix_employees_mcp_token", "mcp_token"),
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_email", "email"),
    )


class EmployeeDepartmentMembership(Base):
    __tablename__ = "employee_department_memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[MembershipRole] = mapped_column(
        SQLAlchemyEnum(
            MembershipRole,
            name="membership_role_enum",
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    capacity_percent: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    active_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    active_to: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    employee: Mapped["Employee"] = relationship(
        "Employee",
        back_populates="memberships",
        foreign_keys=[employee_id],
    )
    department: Mapped["Department"] = relationship(
        "Department",
        back_populates="memberships",
    )

    __table_args__ = (
        CheckConstraint(
            "capacity_percent IS NULL OR capacity_percent BETWEEN 0 AND 100",
            name="ck_membership_capacity_percent_range",
        ),
        UniqueConstraint(
            "employee_id", "department_id", name="uq_membership_employee_department"
        ),
    )


# ---------------------------------------------------------------------------
# Workspaces (Projects) — membership-gated realm
# ---------------------------------------------------------------------------


class Project(Base):
    """
    A named workspace grouping employees and sources across departments.
    Can represent a project, customer engagement, or any cross-functional context.
    Access is purely membership-based — global role does NOT grant access.
    Admin (role='admin') can view all workspaces via workspace:view:all permission.
    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    workspace_type: Mapped[str] = mapped_column(
        String(20),
        default="project",
        comment="project or customer",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        comment="active or archived",
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    project_sources: Mapped[list["ProjectSource"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    created_by: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[created_by_id]
    )


class ProjectMember(Base):
    """Associates an employee with a project/workspace.
    Role determines what the member can do within this workspace.
    """

    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        default=WorkspaceRole.VIEWER.value,
        comment="viewer, contributor, editor, or admin",
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship()

    __table_args__ = (Index("ix_project_members_employee_id", "employee_id"),)


class ProjectSource(Base):
    """Associates a source document with a project."""

    __tablename__ = "project_sources"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="project_sources")
    source: Mapped["Source"] = relationship()

    __table_args__ = (Index("ix_project_sources_source_id", "source_id"),)


# ---------------------------------------------------------------------------
# AI Skills — Versioned prompt packages and tools
# ---------------------------------------------------------------------------


class Skill(Base):
    """
    An AI Skill package (e.g. 'document-generator').
    Can be scoped to a department or global (NULL department).
    """

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope_type: Mapped[str] = mapped_column(
        String(20),
        default="global",
        comment="Scope type: global, project, department, team",
    )
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Scope entity ID. Null for global scope.",
    )
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    version_hash: Mapped[Optional[str]] = mapped_column(String(64))
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(
        PgEnum(
            "active",
            "processing",
            "deleting",
            "deprecated",
            "archived",
            name="skill_status",
        ),
        server_default="active",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    departments: Mapped[list["SkillDepartment"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )
    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillDepartment(Base):
    """Many-to-many: Skill ↔ Department.
    A skill with NO rows here is considered Global (visible to all).
    """

    __tablename__ = "skill_departments"

    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    skill: Mapped["Skill"] = relationship(back_populates="departments")
    department: Mapped["Department"] = relationship(back_populates="skill_departments")


class SkillVersion(Base):
    """Specific version of a skill."""

    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE")
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_hash: Mapped[Optional[str]] = mapped_column(String(64))
    storage_path: Mapped[Optional[str]] = mapped_column(String(1000))
    changelog: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    skill: Mapped["Skill"] = relationship(back_populates="versions")
    author: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (Index("ix_skill_versions_skill_id", "skill_id"),)


# ---------------------------------------------------------------------------
# Scope-based RBAC: Membership & Audit
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """
    Append-only access decision log.
    Records actions for compliance and debugging.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Employee or agent ID",
    )
    principal_type: Mapped[str] = mapped_column(
        String(20),
        default="human",
        comment="human or agent",
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Action attempted (read, list, delete...)",
    )
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of resource: source, wiki_page, etc.",
    )
    resource_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="UUID or identifier of the resource",
    )
    decision: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="allow or deny",
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Human-readable reason for the decision",
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        comment="Extra context (IP, user agent, request ID...)",
    )

    __table_args__ = (
        Index("ix_audit_log_timestamp", "timestamp"),
        Index("ix_audit_log_principal", "principal_id"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )


# ---------------------------------------------------------------------------
# CMD Support — Provinces, Industries, Advisory Sessions
# ---------------------------------------------------------------------------


class Province(Base):
    """Vietnamese province/city (34 units after 2025 merger).

    `assigned_employee_id` points at the HQ contact officer responsible for
    this province; surfaced both in the admin Menu Tổ chức tab and at the
    bottom of every CMD advisory result for the same province.
    """

    __tablename__ = "provinces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    region: Mapped[str] = mapped_column(String(10), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    assigned_employee: Mapped[Optional["Employee"]] = relationship(
        back_populates="assigned_provinces",
        foreign_keys=[assigned_employee_id],
    )

    __table_args__ = (
        Index("ix_provinces_assigned_employee_id", "assigned_employee_id"),
    )


class Industry(Base):
    """VSIC 2018 industry classification (level 1 = 21, level 2 = 88)."""

    __tablename__ = "industries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("industries_level_idx", "level"),
        Index("industries_parent_idx", "parent_code"),
    )


class CmdAdvisorySession(Base):
    """A CMD advisory session — LLM-generated product recommendation for a corporate customer."""

    __tablename__ = "cmd_advisory_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_name: Mapped[str] = mapped_column(String(500), nullable=False)
    province_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    province_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    industry_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    industry_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    customer_segment: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
        comment="Phân khúc KHDN: sme | midcom | public_admin",
    )
    needs: Mapped[str] = mapped_column(Text, nullable=False)
    additional_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_wiki_page_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    retrieved_source_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=list
    )
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    model_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="global")
    scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="ready")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_snapshot_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    retrieval_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reuse_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    refresh_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    created_by: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[created_by_id]
    )

    __table_args__ = (
        Index("cmd_advisory_created_by_idx", "created_by_id"),
        Index("cmd_advisory_created_at_idx", "created_at"),
        # Fix #3: partial unique index serializes concurrent identical requests
        # so two parallel cache-miss inserts can't create duplicate sessions.
        # See alembic/versions/020_cmd_advisory_unique_fingerprint.py.
        Index(
            "cmd_advisory_fingerprint_ready_uniq_idx",
            "input_fingerprint",
            unique=True,
            postgresql_where=text("status = 'ready' AND input_fingerprint IS NOT NULL"),
        ),
    )


# ---------------------------------------------------------------------------
# Native Task Management
# ---------------------------------------------------------------------------


class TaskProject(Base):
    """A native task project scoped to exactly one parent: workspace, department, or employee."""

    __tablename__ = "task_projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    identifier: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "PROJ"
    # XOR parent: exactly one of workspace_id / department_id / owner_employee_id must be set
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        nullable=True,
    )
    owner_employee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    allow_any_employee: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="If True, any active employee can be assigned"
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Optional["Project"]] = relationship(foreign_keys=[workspace_id])
    department: Mapped[Optional["Department"]] = relationship(
        foreign_keys=[department_id]
    )
    owner_employee: Mapped[Optional["Employee"]] = relationship(
        back_populates="personal_task_projects",
        foreign_keys=[owner_employee_id],
    )
    created_by: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[created_by_id]
    )
    states: Mapped[list["TaskState"]] = relationship(
        back_populates="task_project", cascade="all, delete-orphan"
    )
    labels: Mapped[list["TaskLabel"]] = relationship(
        back_populates="task_project", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="task_project", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(workspace_id IS NOT NULL)::int + "
            "(department_id IS NOT NULL)::int + "
            "(owner_employee_id IS NOT NULL)::int = 1",
            name="ck_task_project_scope_xor",
        ),
        Index("ix_task_projects_workspace_id", "workspace_id"),
        Index("ix_task_projects_department_id", "department_id"),
        Index("ix_task_projects_owner_employee_id", "owner_employee_id"),
    )


class TaskState(Base):
    """A workflow state within a task project (e.g., Backlog, Todo, In Progress)."""

    __tablename__ = "task_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    group: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="backlog|todo|in_progress|review|done|cancelled",
    )
    color: Mapped[Optional[str]] = mapped_column(String(20))
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task_project: Mapped["TaskProject"] = relationship(back_populates="states")

    __table_args__ = (Index("ix_task_states_project_id", "task_project_id"),)


class Task(Base):
    """A unit of work in a task project."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_states.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(
        String(20), default="none", comment="none|low|medium|high|urgent"
    )
    parent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    reporter_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1000.0,
        comment="Fractional position within Kanban state lane",
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="Optimistic concurrency version"
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scheduled_start_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    schedule_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task_project: Mapped["TaskProject"] = relationship(
        back_populates="tasks", foreign_keys=[task_project_id]
    )
    state: Mapped["TaskState"] = relationship(foreign_keys=[state_id])
    parent_task: Mapped[Optional["Task"]] = relationship(
        back_populates="subtasks", remote_side="Task.id", foreign_keys=[parent_task_id]
    )
    subtasks: Mapped[list["Task"]] = relationship(
        back_populates="parent_task", foreign_keys=[parent_task_id]
    )
    reporter: Mapped[Optional["Employee"]] = relationship(foreign_keys=[reporter_id])
    created_by: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[created_by_id]
    )
    assignees: Mapped[list["TaskAssignee"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    label_links: Mapped[list["TaskLabelLink"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    comments: Mapped[list["TaskComment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["TaskAttachment"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    activities: Mapped[list["TaskActivity"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_tasks_project_id", "task_project_id"),
        Index("ix_tasks_state_id", "state_id"),
        Index("ix_tasks_parent_task_id", "parent_task_id"),
        Index("ix_tasks_reporter_id", "reporter_id"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_scheduled_start_at", "scheduled_start_at"),
        Index("ix_tasks_deleted_at", "deleted_at"),
        Index("ix_tasks_priority", "priority"),
    )


class TaskAssignee(Base):
    """Many-to-many between Task and Employee."""

    __tablename__ = "task_assignees"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["Task"] = relationship(back_populates="assignees")
    employee: Mapped["Employee"] = relationship(foreign_keys=[employee_id])


class TaskLabel(Base):
    """A label/tag scoped to a task project."""

    __tablename__ = "task_labels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task_project: Mapped["TaskProject"] = relationship(back_populates="labels")

    __table_args__ = (
        UniqueConstraint("task_project_id", "name", name="uq_task_label_project_name"),
        Index("ix_task_labels_project_id", "task_project_id"),
    )


class TaskLabelLink(Base):
    """Many-to-many between Task and TaskLabel."""

    __tablename__ = "task_label_links"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_labels.id", ondelete="CASCADE"),
        primary_key=True,
    )

    task: Mapped["Task"] = relationship(back_populates="label_links")
    label: Mapped["TaskLabel"] = relationship(foreign_keys=[label_id])


class TaskComment(Base):
    """A comment on a task."""

    __tablename__ = "task_comments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task: Mapped["Task"] = relationship(back_populates="comments")
    author: Mapped[Optional["Employee"]] = relationship(foreign_keys=[author_id])

    __table_args__ = (
        Index("ix_task_comments_task_id", "task_id"),
        Index("ix_task_comments_author_id", "author_id"),
    )


class TaskAttachment(Base):
    """A file attachment on a task, stored in MinIO/S3."""

    __tablename__ = "task_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="MinIO/S3 object key — never expose directly",
    )
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["Task"] = relationship(back_populates="attachments")
    uploaded_by: Mapped[Optional["Employee"]] = relationship(
        foreign_keys=[uploaded_by_id]
    )

    __table_args__ = (Index("ix_task_attachments_task_id", "task_id"),)


class TaskActivity(Base):
    """Immutable activity record for a task (state change, assignment, etc.)."""

    __tablename__ = "task_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    verb: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="created|state_changed|assigned|unassigned|commented|attachment_added|attachment_removed|priority_changed|due_date_changed|title_changed|description_changed|label_added|label_removed|archived|restored",
    )
    field_name: Mapped[Optional[str]] = mapped_column(String(100))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    task: Mapped["Task"] = relationship(back_populates="activities")
    actor: Mapped[Optional["Employee"]] = relationship(foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_task_activities_task_id", "task_id"),
        Index("ix_task_activities_created_at", "created_at"),
    )


class PersonalHabit(Base):
    """A recurring personal habit template owned by one employee."""

    __tablename__ = "personal_habits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    priority: Mapped[TaskPriority] = mapped_column(
        SQLAlchemyEnum(
            TaskPriority,
            name="task_priority_enum",
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=TaskPriority.NONE,
        server_default=TaskPriority.NONE.value,
    )
    preferred_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    active_days: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner_employee: Mapped["Employee"] = relationship(
        back_populates="personal_habits",
        foreign_keys=[owner_employee_id],
    )
    occurrences: Mapped[list["HabitOccurrenceState"]] = relationship(
        back_populates="habit", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "duration_minutes >= 1",
            name="ck_personal_habits_duration_minutes_positive",
        ),
        Index("ix_personal_habits_owner_employee_id", "owner_employee_id"),
        Index("ix_personal_habits_is_active", "is_active"),
    )


class HabitOccurrenceState(Base):
    """Per-date completion/skip/shift state for a personal habit."""

    __tablename__ = "habit_occurrence_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    habit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personal_habits.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[HabitOccurrenceStatus] = mapped_column(
        SQLAlchemyEnum(
            HabitOccurrenceStatus,
            name="habit_occurrence_status_enum",
            create_type=False,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
    )
    actual_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    shift_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    habit: Mapped["PersonalHabit"] = relationship(back_populates="occurrences")

    __table_args__ = (
        UniqueConstraint(
            "habit_id",
            "occurrence_date",
            name="uq_habit_occurrence_state_habit_date",
        ),
        Index("ix_habit_occurrence_states_habit_id", "habit_id"),
        Index("ix_habit_occurrence_states_occurrence_date", "occurrence_date"),
    )


class Notification(Base):
    """In-app notification for an employee, polled every 30 seconds."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    notification_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="assigned|mentioned|commented|state_changed|due_soon",
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    recipient: Mapped["Employee"] = relationship(foreign_keys=[recipient_id])
    actor: Mapped[Optional["Employee"]] = relationship(foreign_keys=[actor_id])
    task: Mapped[Optional["Task"]] = relationship(foreign_keys=[task_id])

    __table_args__ = (
        Index("ix_notifications_recipient_id", "recipient_id"),
        Index("ix_notifications_is_read", "is_read"),
        Index("ix_notifications_task_id", "task_id"),
        Index("ix_notifications_created_at", "created_at"),
    )
