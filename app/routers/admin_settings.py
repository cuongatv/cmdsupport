"""
Admin settings router — provider config, connection testing, dashboard stats.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Department, Employee, Source
from app.database.repository import Repository
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_sources: int
    total_departments: int
    total_employees: int


@router.get("/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    repo = Repository(db)
    return DashboardStats(
        total_sources=await repo.count(Source),
        total_departments=await repo.count(Department),
        total_employees=await repo.count(Employee),
    )


# ---------------------------------------------------------------------------
# Settings CRUD
# ---------------------------------------------------------------------------

class SettingsUpdate(BaseModel):
    """Batch update config values."""
    settings: dict[str, str]


class TestConnectionResult(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None


class TestProviderRequest(BaseModel):
    """
    Ad-hoc provider test using values entered in the UI (may be unsaved).

    All fields optional — if any of provider/model_id/api_key is missing,
    the saved DB config for that capability is used as fallback.
    """
    provider: Optional[str] = None
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    dimensions: Optional[int] = None


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    """Get current app settings (masked sensitive values for UI)."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    ui_config = await svc.get_all_for_ui()
    return ui_config


@router.put("/settings")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:manage"),
):
    """Update config values in database."""
    from app.services.config_service import ConfigService

    svc = ConfigService(db)
    results = await svc.set_batch(body.settings)
    
    # Audit log
    keys_updated = list(body.settings.keys())
    await log_audit(db, _user, "update", "settings", "global", reason=f"Updated keys: {', '.join(keys_updated)}")
    await db.commit()
    return {"updated": results}


# ---------------------------------------------------------------------------
# Provider connection testing
# ---------------------------------------------------------------------------

@router.post("/settings/test-providers", response_model=dict[str, TestConnectionResult])
async def test_all_providers(db: AsyncSession = Depends(get_db)):
    """Test all configured AI providers (embedding, LLM, vision)."""
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    results = await registry.test_all()

    return {
        capability: TestConnectionResult(success=ok, message=msg)
        for capability, (ok, msg) in results.items()
    }


async def _build_adhoc_config(
    db: AsyncSession,
    capability: str,
    body: Optional[TestProviderRequest],
):
    """
    Build a ProviderConfig from request body (UI values), falling back to
    saved DB config for any missing field.

    A masked api_key sent from the UI (starts with "•") is treated as
    "use the saved key" — we never echo the masked placeholder to providers.
    """
    from app.ai.providers.base import ProviderConfig, ProviderType
    from app.services.config_service import ConfigService

    svc = ConfigService(db)

    provider_str = (body.provider if body else None) or await svc.get(f"{capability}_provider")
    model_id = (body.model_id if body else None) or await svc.get(f"{capability}_model_id")

    api_key_in = body.api_key if body else None
    if api_key_in and not api_key_in.startswith("•"):
        api_key = api_key_in
    else:
        api_key = await svc.get(f"{capability}_api_key") or ""

    base_url = (body.base_url if body else None) or await svc.get(f"{capability}_base_url")

    if body and body.dimensions is not None:
        dimensions = body.dimensions
    else:
        dim_str = await svc.get(f"{capability}_dimensions")
        dimensions = int(dim_str) if dim_str else None

    if not provider_str or not model_id:
        raise ValueError(
            f"Thiếu thông tin {capability}: cần chọn nhà cung cấp và Model ID."
        )

    return ProviderConfig(
        provider=ProviderType(provider_str),
        api_key=api_key,
        model_id=model_id,
        base_url=base_url,
        dimensions=dimensions,
        extra={},
    )


@router.post("/settings/test-embedding", response_model=TestConnectionResult)
async def test_embedding(
    body: Optional[TestProviderRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Test an embedding provider.

    If a body is supplied (provider/model_id/api_key), tests those values
    directly without saving. Otherwise tests the saved configuration.
    """
    from app.ai.registry import _get_embedding_class

    try:
        config = await _build_adhoc_config(db, "embedding", body)
        config.extra["task"] = "document"
        provider = _get_embedding_class(config.provider)(config)
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-llm", response_model=TestConnectionResult)
async def test_llm(
    body: Optional[TestProviderRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Test an LLM provider.

    If a body is supplied, tests those values directly without saving.
    Otherwise tests the saved configuration.
    """
    from app.ai.registry import _get_llm_class

    try:
        config = await _build_adhoc_config(db, "llm", body)
        provider = _get_llm_class(config.provider)(config)
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


@router.post("/settings/test-vision", response_model=TestConnectionResult)
async def test_vision(
    body: Optional[TestProviderRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Test a vision provider.

    If a body is supplied, tests those values directly without saving.
    Otherwise tests the saved configuration.
    """
    from app.ai.registry import _get_vision_class

    try:
        config = await _build_adhoc_config(db, "vision", body)
        provider = _get_vision_class(config.provider)(config)
        ok, msg = await provider.test_connection()
        return TestConnectionResult(success=ok, message=msg)
    except Exception as e:
        return TestConnectionResult(success=False, message=str(e))


# ---------------------------------------------------------------------------
# Supported providers list (for admin UI dropdowns)
# ---------------------------------------------------------------------------

@router.get("/settings/providers")
async def list_providers():
    """Get supported providers and models for each capability."""
    from app.ai.registry import SUPPORTED_PROVIDERS
    return SUPPORTED_PROVIDERS
