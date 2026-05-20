# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""
Shared pytest fixtures for the CMD Support backend test suite.

Smoke-friendly defaults:
  * Tests should not require an internet connection.
  * Tests that need PostgreSQL skip cleanly when the database is unreachable
    (the `db_session` fixture handles this).
  * Tests that only exercise request/response wiring use `override_db_noop` to
    swap the real `get_db` dependency for a no-op stub so handlers can run
    without any Postgres connection.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date, time

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytest_plugins = ["tests.fixtures.telegram"]


@pytest_asyncio.fixture(autouse=True)
async def _reset_engine_between_tests() -> AsyncIterator[None]:
    """
    Dispose the SQLAlchemy engine pool between tests.

    pytest-asyncio creates a fresh event loop per test by default. Connections
    left in the engine pool by a previous test are bound to that prior loop,
    so the next test fails with "Future attached to a different loop". Calling
    `engine.dispose()` after each test forces fresh, loop-local connections.
    """
    yield
    try:
        from app.database import engine

        await engine.dispose()
    except Exception:
        # Engine may not have been imported in pure-import smoke tests.
        pass


@pytest_asyncio.fixture
async def test_client() -> AsyncIterator[httpx.AsyncClient]:
    """An ASGI-bound httpx client for hitting the FastAPI app in-process."""
    from app.main import app  # imported lazily so test_app_import stays honest

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def admin_token() -> str:
    """Mint a JWT for a synthetic admin (does not touch the database)."""
    from app.services.auth_service import create_access_token

    return create_access_token(
        employee_id=str(uuid.uuid4()),
        role="admin",
        name="Smoke Admin",
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """
    Yield a rollback-isolated async DB session.

    The session is bound to a single connection inside an outer transaction.
    On teardown the transaction is rolled back so the database is left exactly
    as the test found it.

    The fixture skips the test when PostgreSQL is unreachable so smoke runs
    can pass even without Docker.
    """
    from app.database import engine

    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                # Verify the connection is actually live before yielding.
                await session.execute(text("SELECT 1"))
                yield session
            finally:
                await session.close()
                await outer.rollback()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL not reachable: {exc!r}")


@pytest_asyncio.fixture
async def override_db_noop() -> AsyncIterator[None]:
    """
    Replace `app.database.get_db` with a no-op generator so handlers that
    short-circuit before hitting the database can run without Postgres.

    The override is removed on teardown so it does not leak between tests.
    """
    from app.database import get_db
    from app.main import app

    async def _noop():
        # The handler will raise (e.g. 401) before this value is queried.
        yield None

    app.dependency_overrides[get_db] = _noop
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def personal_habit_factory(db_session: AsyncSession):
    """
    Factory fixture for ``PersonalHabit`` rows bound to the rollback session.

    Yields an async callable ``await factory(owner_employee_id, **overrides)``
    that materialises a habit owned by ``owner_employee_id`` with sensible
    defaults (mon-fri 09:00 for 30 minutes, no priority, active). The row is
    flushed onto ``db_session`` but never committed — teardown rolls everything
    back so tests stay isolated.
    """
    from app.database.models import PersonalHabit, TaskPriority

    async def _create(
        owner_employee_id: uuid.UUID,
        *,
        title: str = "Test Habit",
        priority: TaskPriority = TaskPriority.NONE,
        preferred_time: time = time(9, 0),
        duration_minutes: int = 30,
        active_days: list[int] | None = None,
        is_active: bool = True,
    ) -> PersonalHabit:
        habit = PersonalHabit(
            owner_employee_id=owner_employee_id,
            title=title,
            priority=priority,
            preferred_time=preferred_time,
            duration_minutes=duration_minutes,
            active_days=list(active_days)
            if active_days is not None
            else [0, 1, 2, 3, 4],
            is_active=is_active,
        )
        db_session.add(habit)
        await db_session.flush()
        await db_session.refresh(habit)
        return habit

    return _create


@pytest_asyncio.fixture
async def habit_occurrence_factory(db_session: AsyncSession):
    """
    Factory fixture for ``HabitOccurrenceState`` rows bound to the rollback session.

    Yields an async callable ``await factory(habit_id, occurrence_date, **overrides)``
    that materialises a per-date state for the given habit (defaults to
    ``COMPLETED``). Reuses ``db_session`` so teardown rolls everything back.
    """
    from app.database.models import HabitOccurrenceState, HabitOccurrenceStatus

    async def _create(
        habit_id: uuid.UUID,
        occurrence_date: date,
        state: HabitOccurrenceStatus = HabitOccurrenceStatus.COMPLETED,
        *,
        actual_start: time | None = None,
        shift_reason: str | None = None,
    ) -> HabitOccurrenceState:
        row = HabitOccurrenceState(
            habit_id=habit_id,
            occurrence_date=occurrence_date,
            state=state,
            actual_start=actual_start,
            shift_reason=shift_reason,
        )
        db_session.add(row)
        await db_session.flush()
        await db_session.refresh(row)
        return row

    return _create
