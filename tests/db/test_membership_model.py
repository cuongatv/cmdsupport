"""Smoke tests for EmployeeDepartmentMembership model import and tablename."""

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    UnitType,
)


def test_tablename():
    assert EmployeeDepartmentMembership.__tablename__ == "employee_department_memberships"


def test_unit_type_values():
    assert UnitType.BUSINESS_GROUP == "business_group"
    assert UnitType.SQUAD_TEAM == "squad_team"


def test_membership_role_values():
    assert MembershipRole.PRODUCT_OWNER == "product_owner"
    assert MembershipRole.LEAD == "lead"
    assert len(list(MembershipRole)) == 7


def test_department_has_memberships_relationship():
    assert hasattr(Department, "memberships")


def test_employee_has_memberships_relationship():
    assert hasattr(Employee, "memberships")
