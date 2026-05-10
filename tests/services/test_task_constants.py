from app.services import task_constants


def test_hierarchy_limit_is_frozen() -> None:
    assert task_constants.MAX_SUBTASK_DEPTH == 1


def test_content_limits_are_frozen() -> None:
    assert task_constants.MAX_DESCRIPTION_BYTES == 65_536
    assert task_constants.MAX_ATTACHMENT_BYTES == 26_214_400
    assert task_constants.MAX_ATTACHMENTS_PER_TASK == 10


def test_notification_and_version_defaults_are_frozen() -> None:
    assert task_constants.NOTIFICATION_POLL_INTERVAL_SECONDS == 30
    assert task_constants.INITIAL_TASK_VERSION == 1


def test_default_states_and_groups_are_zip_compatible() -> None:
    assert len(task_constants.DEFAULT_STATE_NAMES) == 6
    assert len(task_constants.DEFAULT_STATE_GROUPS) == 6
    assert len(task_constants.DEFAULT_STATE_NAMES) == len(task_constants.DEFAULT_STATE_GROUPS)
    assert "Backlog" in task_constants.DEFAULT_STATE_NAMES
    assert "Cancelled" in task_constants.DEFAULT_STATE_NAMES


def test_priority_levels_include_minimum_and_maximum() -> None:
    assert "none" in task_constants.PRIORITY_LEVELS
    assert "urgent" in task_constants.PRIORITY_LEVELS


def test_kanban_position_gap_is_positive() -> None:
    assert task_constants.POSITION_GAP > 0
