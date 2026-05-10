from app.services.permissions import ALL_PERMISSIONS, EMPLOYEE_DEFAULT_PERMISSIONS


TASK_PERMISSIONS = [
    "task:read:own_dept",
    "task:read:all",
    "task:create:own_dept",
    "task:create:all",
    "task:edit:own_dept",
    "task:edit:all",
    "task:delete:own_dept",
    "task:delete:all",
    "task_project:manage:own_dept",
    "task_project:manage:all",
]


def test_task_permissions_catalog() -> None:
    for permission in TASK_PERMISSIONS:
        assert permission in ALL_PERMISSIONS


def test_task_permissions_have_own_dept_and_all_variants() -> None:
    expected_pairs = [
        ("task", "read"),
        ("task", "create"),
        ("task", "edit"),
        ("task", "delete"),
        ("task_project", "manage"),
    ]

    for resource, action in expected_pairs:
        assert f"{resource}:{action}:own_dept" in ALL_PERMISSIONS
        assert f"{resource}:{action}:all" in ALL_PERMISSIONS


def test_employee_default_includes_task_read() -> None:
    assert "task:read:own_dept" in EMPLOYEE_DEFAULT_PERMISSIONS


def test_existing_permissions_not_regressed() -> None:
    assert "doc:read:own_dept" in ALL_PERMISSIONS
    assert "wiki:read:own_dept" in ALL_PERMISSIONS
    assert "org:departments:read" in ALL_PERMISSIONS
