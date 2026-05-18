from app.services.permissions import (
    ALL_PERMISSIONS,
    EMPLOYEE_DEFAULT_PERMISSIONS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_GROUPS,
    PERMISSION_LABELS,
)

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


# Phase 5 governance — the five strings introduced in T20. Listed verbatim so
# the test fails loudly if any rename slips through the catalogue.
AGILE_GOVERNANCE_PERMISSIONS = [
    "agile.sprint.create",
    "agile.sprint.close",
    "agile.wip.override",
    "agile.dod.bypass",
    "agile.governance.advisory.read",
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


def test_agile_permissions_registered() -> None:
    """Phase 5 governance: every Agile string lives in every catalogue.

    The four catalogues (``ALL_PERMISSIONS``, labels, descriptions, and the
    UI group mapping) must each carry every one of the five strings.
    Diverging catalogues silently degrade the Settings UI, so the test
    asserts each invariant separately for a clearer failure message.
    """
    # ALL_PERMISSIONS — the authoritative flat list.
    for permission in AGILE_GOVERNANCE_PERMISSIONS:
        assert permission in ALL_PERMISSIONS, (
            f"missing from ALL_PERMISSIONS: {permission}"
        )

    # Vietnamese label catalogue used by the Settings UI.
    for permission in AGILE_GOVERNANCE_PERMISSIONS:
        assert permission in PERMISSION_LABELS, (
            f"missing label: {permission}"
        )
        assert PERMISSION_LABELS[permission].strip(), (
            f"empty label: {permission}"
        )

    # Tooltip / description catalogue.
    for permission in AGILE_GOVERNANCE_PERMISSIONS:
        assert permission in PERMISSION_DESCRIPTIONS, (
            f"missing description: {permission}"
        )
        assert PERMISSION_DESCRIPTIONS[permission].strip(), (
            f"empty description: {permission}"
        )

    # Group mapping — must live under a single coherent group so the Settings
    # UI renders a contiguous Agile section.
    grouped_permissions = {
        permission
        for permissions in PERMISSION_GROUPS.values()
        for permission in permissions
    }
    for permission in AGILE_GOVERNANCE_PERMISSIONS:
        assert permission in grouped_permissions, (
            f"missing from PERMISSION_GROUPS: {permission}"
        )

    # All five strings must share a single group (no scattered duplicates).
    owning_groups = {
        group
        for group, permissions in PERMISSION_GROUPS.items()
        if any(p in permissions for p in AGILE_GOVERNANCE_PERMISSIONS)
    }
    assert len(owning_groups) == 1, (
        f"agile permissions split across groups: {owning_groups}"
    )
