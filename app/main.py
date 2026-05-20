# pyright: reportMissingImports=false
"""
CMD Support — Trợ lý Tư vấn Khách hàng Doanh nghiệp.
FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.mcp.server import create_mcp_server

# Create the MCP server and its HTTP app (lifespan must be composed with FastAPI)
mcp_server = create_mcp_server()
mcp_http_app = mcp_server.http_app(path="/", stateless_http=True)


async def seed_default_admin():
    """Create default admin account from .env if no admin exists yet."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.database.models import Department, Employee
    from app.services.auth_service import hash_password

    try:
        async with async_session_factory() as session:
            # Check if any admin already exists
            stmt = select(Employee).where(Employee.role == "admin").limit(1)
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                return  # Admin already exists, skip

            # Create admin department
            dept = Department(
                name="Administration", description="System administrators"
            )
            session.add(dept)
            await session.flush()

            # Create admin user from .env. Username defaults to the email
            # local-part so the new login form works out of the box.
            admin_username = settings.default_admin_email.split("@")[0].lower()
            admin = Employee(
                name="Admin",
                email=settings.default_admin_email,
                username=admin_username or "admin",
                password_hash=hash_password(settings.default_admin_password),
                role="admin",
                department_id=dept.id,
            )
            session.add(admin)
            await session.flush()

            await session.commit()
            logger.success(f"Default admin created: {settings.default_admin_email}")
    except Exception as e:
        logger.warning(f"Could not seed default admin: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown logic (composed with FastMCP lifespan)."""
    async with mcp_http_app.lifespan(app):
        logger.info("Starting CMD Support API...")

        # Ensure MinIO bucket exists
        try:
            from app.services.storage_service import storage_service

            await storage_service.ensure_bucket()
            logger.success("MinIO bucket ready")
        except Exception as e:
            logger.warning(f"MinIO not available yet: {e}")

        # Seed default admin if no admin exists yet
        await seed_default_admin()

        # Warn if sensitive defaults are unchanged
        if settings.secret_key == "change-me-to-a-random-secret-string":
            logger.warning(
                "⚠️  SECRET_KEY is set to the default value — change it before deploying to production!"
            )
        if settings.default_admin_password == "admin123":
            logger.warning(
                "⚠️  DEFAULT_ADMIN_PASSWORD is 'admin123' — change the admin password after first login!"
            )

        # MCP server ready
        logger.success("CMD Support MCP Server ready at /mcp")
        logger.success("CMD Support API started successfully")
        yield

        logger.info("CMD Support API shutdown complete")


app = FastAPI(
    title="CMD Support API",
    description="Trợ lý Tư vấn Khách hàng Doanh nghiệp — Quản lý Tri thức & Kỹ năng AI",
    version="0.1.0",
    lifespan=lifespan,
)

# --- CORS ---
logger.info(f"Allowed CORS origins: {settings.cors_origin_list}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mount MCP Server ---
# Claude Desktop connects to: https://your-server/mcp
app.mount("/mcp", mcp_http_app)

# --- REST API Routers ---
from app.routers import (  # noqa: E402
    admin_dashboard_router,
    admin_settings,
    agile_capacity_router,
    audit,
    auth,
    cmd_support,
    consulting_rules,
    departments,
    flow_metrics_router,
    habits,
    idea_submissions,
    knowledge_types,
    notes,
    notifications,
    projects,
    rbac,
    roles,
    scopes_gone,
    skills,
    sources,
    sprint_router,
    tasks,
    telegram_admin,
    telegram_bindings,
    telegram_identities,
    telegram_webhook,
    wiki,
    wiki_drafts,
    wiki_reclassify,
)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(sources.router, prefix="/api", tags=["sources"])
app.include_router(notes.router, prefix="/api", tags=["notes"])
app.include_router(wiki_drafts.router, prefix="/api", tags=["wiki-drafts"])
app.include_router(wiki.router, prefix="/api", tags=["wiki"])
app.include_router(wiki_reclassify.router, prefix="/api", tags=["wiki-reclassify"])
app.include_router(admin_settings.router, prefix="/api", tags=["settings"])
app.include_router(rbac.router, prefix="/api", tags=["rbac"])
app.include_router(departments.router, prefix="/api", tags=["departments"])
app.include_router(scopes_gone.router, prefix="/api", tags=["scopes-gone"])
app.include_router(knowledge_types.router, prefix="/api", tags=["knowledge-types"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(roles.router, prefix="/api", tags=["roles"])
app.include_router(audit.router, prefix="/api", tags=["audit"])
app.include_router(skills.router, prefix="/api", tags=["skills"])
app.include_router(cmd_support.router, prefix="/api", tags=["cmd-support"])
app.include_router(consulting_rules.router, prefix="/api", tags=["consulting-rules"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(
    telegram_webhook.router, prefix="/api", tags=["telegram-webhook"]
)
app.include_router(sprint_router.router, prefix="/api", tags=["sprints"])
app.include_router(
    agile_capacity_router.router, prefix="/api", tags=["agile-capacity"]
)
app.include_router(flow_metrics_router.router, prefix="/api", tags=["flow-metrics"])
app.include_router(
    admin_dashboard_router.router, prefix="/api", tags=["admin-dashboard"]
)
app.include_router(notifications.router, prefix="/api", tags=["notifications"])
app.include_router(habits.router, prefix="/api", tags=["habits"])
app.include_router(idea_submissions.router, prefix="/api", tags=["idea-submissions"])
app.include_router(telegram_admin.router, prefix="/api", tags=["telegram-admin"])
app.include_router(telegram_bindings.router, prefix="/api", tags=["telegram-bindings"])
app.include_router(
    telegram_identities.router, prefix="/api", tags=["telegram-identities"]
)


@app.get("/")
async def root():
    return {
        "name": "CMD Support",
        "description": "Trợ lý Tư vấn Khách hàng Doanh nghiệp BIDV",
        "version": "0.1.0",
        "mcp_endpoint": "/mcp",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    services = {}
    overall = "healthy"

    # Database
    try:
        from sqlalchemy import text

        from app.database import async_session_factory

        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = "error"
        overall = "degraded"
        logger.warning(f"Health check — database error: {e}")

    # Redis
    try:
        from app.routers.sources import get_arq_pool

        pool = await get_arq_pool()
        await pool.ping()
        services["redis"] = "healthy"
    except Exception as e:
        services["redis"] = "error"
        overall = "degraded"
        logger.warning(f"Health check — redis error: {e}")

    # MinIO
    try:
        from app.services.storage_service import storage_service

        await storage_service.ensure_bucket()
        services["minio"] = "healthy"
    except Exception as e:
        services["minio"] = "error"
        overall = "degraded"
        logger.warning(f"Health check — minio error: {e}")

    return {"status": overall, "services": services}


@app.get("/api/health")
async def api_health():
    """Detailed health check for API, database, and worker (Redis)."""
    from sqlalchemy import text

    from app.database import async_session_factory

    result = {
        "api": "healthy",
        "database": "error",
        "worker": "error",
    }

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        result["database"] = "healthy"
    except Exception as e:
        logger.warning(f"Health check: DB error — {e}")

    try:
        import redis.asyncio as aioredis

        r = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            socket_connect_timeout=2,
        )
        await r.ping()
        await r.aclose()
        result["worker"] = "healthy"
    except Exception as e:
        logger.warning(f"Health check: Redis error — {e}")

    return result
