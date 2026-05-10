"""
Auth Service — JWT-based authentication for Admin Portal and Employee Portal.

Handles:
  - Password hashing (bcrypt)
  - JWT token generation and verification
  - Login / logout (stateless JWT)
  - Role-based access (admin vs employee)
  - Scoped permission checks (v2: resource:action:scope format)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.database.models import Employee

# JWT config
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(employee_id: str, role: str, name: str) -> str:
    """Create a signed JWT token."""
    payload = {
        "sub": employee_id,
        "role": role,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Login / authenticate
# ---------------------------------------------------------------------------

async def authenticate_employee(
    db: AsyncSession, email: str, password: str
) -> Optional[Employee]:
    """
    Verify email + password. Returns Employee or None.
    """
    stmt = (
        select(Employee)
        .where(Employee.email == email, Employee.is_active.is_(True))
        .options(selectinload(Employee.department), selectinload(Employee.custom_role))
    )
    result = await db.execute(stmt)
    employee = result.scalar_one_or_none()

    if not employee or not employee.password_hash:
        return None
    if not verify_password(password, employee.password_hash):
        return None
    return employee


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    """
    FastAPI dependency — extracts and validates JWT from Authorization header.
    Returns the authenticated Employee.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.department), selectinload(Employee.custom_role))
        .where(Employee.id == uuid.UUID(payload["sub"]))
    )
    employee = result.scalar_one_or_none()
    if not employee or not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or deactivated",
        )

    # Auto-attach the "Employee" system role if no custom role assigned
    if employee.role == "employee" and not employee.custom_role:
        from app.database.models import Role
        sys_role = (await db.execute(
            select(Role).where(Role.name == "Employee", Role.is_system.is_(True))
        )).scalar_one_or_none()
        if sys_role:
            employee.custom_role = sys_role

    return employee


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[Employee]:
    """
    Like get_current_user but returns None instead of raising 401
    when credentials are missing or invalid. Used for public endpoints
    that optionally benefit from knowing who the caller is.
    """
    if not credentials:
        return None

    payload = decode_access_token(credentials.credentials)
    if not payload:
        return None

    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.department), selectinload(Employee.custom_role))
        .where(Employee.id == uuid.UUID(payload["sub"]))
    )
    employee = result.scalar_one_or_none()
    if not employee or not employee.is_active:
        return None

    if employee.role == "employee" and not employee.custom_role:
        from app.database.models import Role
        sys_role = (await db.execute(
            select(Role).where(Role.name == "Employee", Role.is_system.is_(True))
        )).scalar_one_or_none()
        if sys_role:
            employee.custom_role = sys_role

    return employee


async def require_admin(
    current_user: Employee = Depends(get_current_user),
) -> Employee:
    """
    FastAPI dependency — requires admin role.
    Use on admin-only endpoints.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_permission(permission: str):
    """
    FastAPI dependency factory — checks a specific permission on the employee's custom role.
    Admins bypass all permission checks.
    
    Supports both new scoped format (doc:read:own_dept) and org permissions (org:settings:read).
    
    For scoped resource permissions (doc/wiki), this only checks that the user
    has SOME variant (own_dept or all). Actual scope filtering (which documents
    they can see) is handled by the permission engine at query time.

    Usage: Depends(require_permission("doc:read"))  — checks for doc:read:own_dept OR doc:read:all
           Depends(require_permission("org:settings:read"))  — exact match
    """
    async def _check(current_user: Employee = Depends(get_current_user)) -> Employee:
        if current_user.role == "admin":
            return current_user

        from app.services.permission_engine import (
            _get_user_permissions,
            has_any_permission,
        )
        effective = _get_user_permissions(current_user)

        # Check exact match first (for org: permissions)
        if permission in effective:
            return current_user

        # Check as resource:action (matches either :own_dept or :all)
        parts = permission.split(":")
        if len(parts) == 2:
            resource, action = parts
            if has_any_permission(list(effective), resource, action):
                return current_user
        elif len(parts) == 3:
            # Exact scoped permission check
            if permission in effective:
                return current_user
            # Also check if user has the :all version when :own_dept is required
            resource, action, scope = parts
            if scope == "own_dept" and f"{resource}:{action}:all" in effective:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission}",
        )
    return Depends(_check)
