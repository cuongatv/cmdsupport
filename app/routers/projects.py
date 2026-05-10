"""
Projects router — cross-functional knowledge contexts.

A Project groups employees and sources across departments for a specific purpose
(client engagement, event, initiative). Only project members and admins can access
project-scoped sources via MCP.

Permission model:
  - Create workspace: system admin only
  - Update workspace (rename/archive): workspace admin OR system admin
  - Delete workspace: system admin only
  - View members/sources/wiki: any workspace member (viewer+)
  - Manage sources (add/remove/upload): workspace editor+
  - Manage members: workspace admin
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import (
    Employee,
    Project,
    ProjectMember,
    ProjectSource,
    Source,
    WorkspaceRole,
)
from app.services.auth_service import (
    get_current_user,
)
from app.services.permission_engine import (
    can_access_workspace,
    get_workspace_role,
    workspace_role_can,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    workspace_type: Optional[str] = "project"  # "project" or "customer"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # "active" or "archived"
    workspace_type: Optional[str] = None  # "project" or "customer"


class ProjectOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    workspace_type: str = "project"
    status: str
    member_count: int = 0
    source_count: int = 0
    created_at: str

    class Config:
        from_attributes = True


class MemberOut(BaseModel):
    employee_id: str
    employee_name: str
    employee_email: str
    role: str
    added_at: str


class ProjectSourceOut(BaseModel):
    source_id: str
    title: Optional[str]
    source_type: Optional[str]
    file_name: Optional[str] = None
    status: str
    progress: Optional[int] = None
    progress_message: Optional[str] = None
    knowledge_type_name: Optional[str] = None
    added_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_project_or_404(db: AsyncSession, project_id: str) -> Project:
    project = await db.get(Project, uuid.UUID(project_id))
    if not project:
        raise HTTPException(404, "Project not found")
    return project


async def _require_workspace_member(db: AsyncSession, user: Employee, project_id: str) -> None:
    """Raise 403 if user is not a workspace member (or system admin)."""
    if not await can_access_workspace(db, user, uuid.UUID(project_id)):
        raise HTTPException(403, "Workspace access required")


async def _require_workspace_role(
    db: AsyncSession, user: Employee, project_id: str, min_role: str
) -> str:
    """Raise 403 if user's workspace role is below min_role. Returns the role."""
    ws_role = await get_workspace_role(db, user, uuid.UUID(project_id))
    if not ws_role or not workspace_role_can(ws_role, min_role):
        labels = {
            WorkspaceRole.VIEWER.value: "viewer",
            WorkspaceRole.CONTRIBUTOR.value: "contributor",
            WorkspaceRole.EDITOR.value: "editor",
            WorkspaceRole.ADMIN.value: "admin",
        }
        raise HTTPException(403, f"Workspace {labels.get(min_role, min_role)} access required")
    return ws_role


async def _count_workspace_admins(db: AsyncSession, project_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == uuid.UUID(project_id),
            ProjectMember.role == WorkspaceRole.ADMIN.value,
        )
    )
    return result.scalar() or 0


def _project_out(project: Project, member_count: int = 0, source_count: int = 0) -> ProjectOut:
    return ProjectOut(
        id=str(project.id),
        name=project.name,
        description=project.description,
        workspace_type=getattr(project, 'workspace_type', 'project') or 'project',
        status=project.status,
        member_count=member_count,
        source_count=source_count,
        created_at=project.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Admin: returns all projects.
    Employee: returns only projects they are a member of.
    """
    if current_user.role == "admin":
        result = await db.execute(select(Project).order_by(Project.created_at.desc()))
        projects = result.scalars().all()
    else:
        result = await db.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.employee_id == current_user.id)
            .order_by(Project.created_at.desc())
        )
        projects = result.scalars().all()

    # Fetch counts in bulk
    member_counts_result = await db.execute(
        select(ProjectMember.project_id, func.count(ProjectMember.employee_id))
        .group_by(ProjectMember.project_id)
    )
    member_counts = {str(r[0]): r[1] for r in member_counts_result.all()}

    linked_counts_result = await db.execute(
        select(ProjectSource.project_id, func.count(ProjectSource.source_id))
        .group_by(ProjectSource.project_id)
    )
    linked_counts = {str(r[0]): r[1] for r in linked_counts_result.all()}

    owned_counts_result = await db.execute(
        select(Source.scope_id, func.count(Source.id))
        .where(Source.scope_type == "project", Source.scope_id.isnot(None))
        .group_by(Source.scope_id)
    )
    owned_counts = {str(r[0]): r[1] for r in owned_counts_result.all()}

    all_project_ids = set(linked_counts.keys()) | set(owned_counts.keys())
    source_counts: dict[str, int] = {}
    for pid_str in all_project_ids:
        source_counts[pid_str] = max(linked_counts.get(pid_str, 0), owned_counts.get(pid_str, 0))

    return [
        _project_out(p, member_counts.get(str(p.id), 0), source_counts.get(str(p.id), 0))
        for p in projects
    ]


@router.post("/projects", status_code=201, response_model=ProjectOut)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required to create workspaces")

    ws_type = body.workspace_type or "project"
    if ws_type not in ("project", "customer"):
        raise HTTPException(400, "workspace_type must be 'project' or 'customer'")

    project = Project(
        name=body.name,
        description=body.description,
        workspace_type=ws_type,
        status="active",
        created_by_id=current_user.id,
    )
    db.add(project)
    await db.flush()

    # Creator becomes workspace admin member
    member = ProjectMember(
        project_id=project.id,
        employee_id=current_user.id,
        role=WorkspaceRole.ADMIN.value,
    )
    db.add(member)
    await db.flush()

    return _project_out(project)


@router.put("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _get_project_or_404(db, project_id)
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.ADMIN.value)

    project = await _get_project_or_404(db, project_id)
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.workspace_type is not None:
        if body.workspace_type not in ("project", "customer"):
            raise HTTPException(400, "workspace_type must be 'project' or 'customer'")
        project.workspace_type = body.workspace_type
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(400, "Status must be 'active' or 'archived'")
        project.status = body.status

    await db.flush()
    return _project_out(project)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    if _user.role != "admin":
        raise HTTPException(403, "Only system admins can delete workspaces")

    project = await _get_project_or_404(db, project_id)
    await db.delete(project)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

class AddMemberBody(BaseModel):
    employee_id: str
    role: str = "viewer"


class UpdateMemberBody(BaseModel):
    role: str


@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    await _get_project_or_404(db, project_id)
    await _require_workspace_member(db, current_user, project_id)

    result = await db.execute(
        select(ProjectMember)
        .options(selectinload(ProjectMember.employee))
        .where(ProjectMember.project_id == uuid.UUID(project_id))
    )
    members = result.scalars().all()
    return [
        MemberOut(
            employee_id=str(m.employee_id),
            employee_name=m.employee.name,
            employee_email=m.employee.email,
            role=m.role,
            added_at=m.added_at.isoformat(),
        )
        for m in members
    ]


@router.post("/projects/{project_id}/members", status_code=201)
async def add_member(
    project_id: str,
    body: AddMemberBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _get_project_or_404(db, project_id)
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.ADMIN.value)

    emp = await db.get(Employee, uuid.UUID(body.employee_id))
    if not emp:
        raise HTTPException(404, "Employee not found")

    existing = await db.get(
        ProjectMember,
        (uuid.UUID(project_id), uuid.UUID(body.employee_id)),
    )
    if existing:
        raise HTTPException(409, "Employee is already a member")

    valid_roles = {r.value for r in WorkspaceRole}
    if body.role not in valid_roles:
        raise HTTPException(400, f"Role must be one of: {sorted(valid_roles)}")

    member = ProjectMember(
        project_id=uuid.UUID(project_id),
        employee_id=uuid.UUID(body.employee_id),
        role=body.role,
    )
    db.add(member)
    await db.flush()
    return {"added": True}


@router.delete("/projects/{project_id}/members/{employee_id}")
async def remove_member(
    project_id: str,
    employee_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.ADMIN.value)

    member = await db.get(
        ProjectMember,
        (uuid.UUID(project_id), uuid.UUID(employee_id)),
    )
    if not member:
        raise HTTPException(404, "Member not found")

    # Guard: cannot remove the last workspace admin
    if member.role == WorkspaceRole.ADMIN.value:
        if await _count_workspace_admins(db, project_id) <= 1:
            raise HTTPException(400, "Cannot remove the last workspace admin")

    await db.delete(member)
    return {"removed": True}


@router.patch("/projects/{project_id}/members/{employee_id}")
async def update_member(
    project_id: str,
    employee_id: str,
    body: UpdateMemberBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.ADMIN.value)

    member = await db.get(
        ProjectMember,
        (uuid.UUID(project_id), uuid.UUID(employee_id)),
    )
    if not member:
        raise HTTPException(404, "Member not found")

    valid_roles = {r.value for r in WorkspaceRole}
    if body.role not in valid_roles:
        raise HTTPException(400, f"Role must be one of: {sorted(valid_roles)}")

    # Guard: cannot demote the last workspace admin
    if member.role == WorkspaceRole.ADMIN.value and body.role != WorkspaceRole.ADMIN.value:
        if await _count_workspace_admins(db, project_id) <= 1:
            raise HTTPException(400, "Cannot demote the last workspace admin")

    member.role = body.role
    await db.flush()
    return {"updated": True}


# ---------------------------------------------------------------------------
# Project Sources
# ---------------------------------------------------------------------------

class AddSourceBody(BaseModel):
    source_id: str


@router.get("/projects/{project_id}/sources", response_model=list[ProjectSourceOut])
async def list_project_sources(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    await _get_project_or_404(db, project_id)
    await _require_workspace_member(db, current_user, project_id)

    pid = uuid.UUID(project_id)

    # 1. Linked sources (project_sources table)
    linked_result = await db.execute(
        select(ProjectSource)
        .options(
            selectinload(ProjectSource.source).selectinload(Source.knowledge_type)
        )
        .where(ProjectSource.project_id == pid)
    )
    linked_rows = linked_result.scalars().all()
    linked_ids = {r.source_id for r in linked_rows}

    # 2. Owned sources (scope_type=project, scope_id=project_id)
    owned_result = await db.execute(
        select(Source)
        .options(selectinload(Source.knowledge_type))
        .where(Source.scope_type == "project", Source.scope_id == pid)
    )
    owned_sources = owned_result.scalars().all()

    out: list[ProjectSourceOut] = []
    for r in linked_rows:
        out.append(ProjectSourceOut(
            source_id=str(r.source_id),
            title=r.source.title,
            source_type=r.source.source_type,
            file_name=r.source.file_name,
            status=r.source.status,
            progress=r.source.progress,
            progress_message=r.source.progress_message,
            knowledge_type_name=r.source.knowledge_type.name if r.source.knowledge_type else None,
            added_at=r.added_at.isoformat(),
        ))
    for s in owned_sources:
        if s.id not in linked_ids:
            out.append(ProjectSourceOut(
                source_id=str(s.id),
                title=s.title,
                source_type=s.source_type,
                file_name=s.file_name,
                status=s.status,
                progress=s.progress,
                progress_message=s.progress_message,
                knowledge_type_name=s.knowledge_type.name if s.knowledge_type else None,
                added_at=s.created_at.isoformat(),
            ))
    return out


@router.post("/projects/{project_id}/sources", status_code=201)
async def add_project_source(
    project_id: str,
    body: AddSourceBody,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _get_project_or_404(db, project_id)
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.EDITOR.value)

    source = await db.get(Source, uuid.UUID(body.source_id))
    if not source:
        raise HTTPException(404, "Source not found")

    existing = await db.get(
        ProjectSource,
        (uuid.UUID(project_id), uuid.UUID(body.source_id)),
    )
    if existing:
        raise HTTPException(409, "Source already in project")

    ps = ProjectSource(
        project_id=uuid.UUID(project_id),
        source_id=uuid.UUID(body.source_id),
    )
    db.add(ps)
    await db.flush()
    return {"added": True}


@router.delete("/projects/{project_id}/sources/{source_id}")
async def remove_project_source(
    project_id: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    await _require_workspace_role(db, _user, project_id, WorkspaceRole.EDITOR.value)

    pid = uuid.UUID(project_id)
    sid = uuid.UUID(source_id)

    # 1. Check linked source (project_sources join table)
    ps = await db.get(ProjectSource, (pid, sid))
    if ps:
        await db.delete(ps)
        return {"removed": True}

    # 2. Check owned source (scope_type=project, scope_id=project_id)
    source = await db.get(Source, sid)
    if source and source.scope_type == "project" and source.scope_id == pid:
        await db.delete(source)
        return {"removed": True}

    raise HTTPException(404, "Source not in project")


# ---------------------------------------------------------------------------
# Workspace-scoped upload (owned sources)
# ---------------------------------------------------------------------------

from arq.connections import ArqRedis, create_pool  # noqa: E402
from fastapi import File, Form, UploadFile  # noqa: E402

_arq_pool_ws: ArqRedis | None = None

async def _get_arq_pool() -> ArqRedis:
    global _arq_pool_ws
    if _arq_pool_ws is None:
        from app.worker import _get_redis_settings
        _arq_pool_ws = await create_pool(_get_redis_settings())
    return _arq_pool_ws


@router.post("/projects/{project_id}/sources/upload", status_code=201)
async def upload_workspace_source(
    project_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    knowledge_type_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Upload a file directly into a workspace. Requires editor+ role."""
    await _get_project_or_404(db, project_id)
    await _require_workspace_role(db, user, project_id, WorkspaceRole.EDITOR.value)

    pid = uuid.UUID(project_id)
    file_data = await file.read()
    file_name = file.filename or "unknown"

    source = Source(
        title=title or file.filename,
        source_type="file",
        file_name=file_name,
        file_size=len(file_data),
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=uuid.UUID(knowledge_type_id) if knowledge_type_id else None,
        contributed_by_employee_id=user.id,
        scope_type="project",
        scope_id=pid,
    )
    db.add(source)
    await db.flush()

    from app.services.kb_service import _guess_content_type
    from app.services.storage_service import storage_service
    minio_key = f"sources/{source.id}/original/{file_name}"
    storage_service.upload_file(
        object_name=minio_key,
        data=file_data,
        content_type=_guess_content_type(file_name),
    )
    source.minio_key = minio_key
    source.file_name = file_name
    await db.flush()

    pool = await _get_arq_pool()
    job = await pool.enqueue_job("ingest_file_task", str(source.id))
    source.job_id = job.job_id
    await db.commit()

    return {
        "id": str(source.id),
        "title": source.title,
        "status": source.status,
        "scope_type": source.scope_type,
        "scope_id": str(source.scope_id),
    }


class WorkspaceURLBody(BaseModel):
    url: str
    title: str | None = None
    knowledge_type_id: str | None = None


@router.post("/projects/{project_id}/sources/url", status_code=201)
async def add_workspace_url_source(
    project_id: str,
    body: WorkspaceURLBody,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Add a URL source directly into a workspace. Requires editor+ role."""
    await _get_project_or_404(db, project_id)
    await _require_workspace_role(db, user, project_id, WorkspaceRole.EDITOR.value)

    pid = uuid.UUID(project_id)

    source = Source(
        title=body.title or body.url,
        source_type="url",
        url=body.url,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=uuid.UUID(body.knowledge_type_id) if body.knowledge_type_id else None,
        contributed_by_employee_id=user.id,
        scope_type="project",
        scope_id=pid,
    )
    db.add(source)
    await db.flush()

    pool = await _get_arq_pool()
    job = await pool.enqueue_job("ingest_url_task", str(source.id))
    source.job_id = job.job_id
    await db.commit()

    return {
        "id": str(source.id),
        "title": source.title,
        "status": source.status,
        "scope_type": source.scope_type,
        "scope_id": str(source.scope_id),
    }


# ---------------------------------------------------------------------------
# Workspace Wiki
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/wiki")
async def list_workspace_wiki(
    project_id: str,
    page_type: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """List wiki pages scoped to this workspace. Requires workspace membership."""
    await _get_project_or_404(db, project_id)
    await _require_workspace_member(db, current_user, project_id)

    pid = uuid.UUID(project_id)
    from app.services import wiki_service
    pages = await wiki_service.list_pages(
        db,
        page_type=page_type,
        limit=limit,
        scope_type="project",
        scope_id=pid,
    )
    return [
        {
            "slug": p.slug,
            "title": p.title,
            "page_type": p.page_type,
            "summary": p.summary,
            "knowledge_type_slugs": p.knowledge_type_slugs or [],
            "source_ids": [str(s) for s in (p.source_ids or [])],
            "scope_type": p.scope_type,
            "scope_id": str(p.scope_id) if p.scope_id else None,
            "version": p.version or 1,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in pages
    ]


@router.get("/projects/{project_id}/wiki/index")
async def get_workspace_wiki_index(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Get wiki index page scoped to this workspace. Requires workspace membership."""
    await _get_project_or_404(db, project_id)
    await _require_workspace_member(db, current_user, project_id)

    pid = uuid.UUID(project_id)
    from app.services import wiki_service
    page = await wiki_service.get_page_by_slug(
        db, wiki_service.INDEX_SLUG,
        scope_type="project", scope_id=pid,
    )
    return {"content_md": page.content_md if page else ""}


@router.get("/projects/{project_id}/wiki/graph")
async def get_workspace_wiki_graph(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Return nodes/edges for workspace-scoped wiki graph. Requires workspace membership."""
    await _get_project_or_404(db, project_id)
    await _require_workspace_member(db, current_user, project_id)

    pid = uuid.UUID(project_id)

    from app.database.models import WikiLink, WikiPage
    from app.services import wiki_service

    pages = (await db.execute(
        select(WikiPage.slug, WikiPage.title, WikiPage.page_type)
        .where(
            WikiPage.scope_type == "project",
            WikiPage.scope_id == pid,
            WikiPage.slug.notin_([wiki_service.INDEX_SLUG, wiki_service.LOG_SLUG]),
        )
    )).all()

    slug_set = {r.slug for r in pages}

    edges = (await db.execute(select(WikiLink.from_slug, WikiLink.to_slug))).all()

    return {
        "nodes": [{"slug": r.slug, "title": r.title, "page_type": r.page_type} for r in pages],
        "edges": [
            {"from": r.from_slug, "to": r.to_slug}
            for r in edges
            if r.from_slug in slug_set and r.to_slug in slug_set
        ],
    }
