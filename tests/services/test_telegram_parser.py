from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false, reportUnknownVariableType=false
from collections.abc import Mapping

import pytest

from app.integrations.telegram.parser import (
    CommandKind,
    MentionTarget,
    ParsedCommand,
    parse_message,
)


@pytest.mark.parametrize(
    (
        "message",
        "bot_username",
        "expected",
    ),
    [
        pytest.param(
            {"text": "/help", "entities": [{"type": "bot_command", "offset": 0, "length": 5}]},
            None,
            ParsedCommand(
                kind=CommandKind.HELP,
                raw_text="/help",
                args="",
                mentions=(),
                validation_error=None,
            ),
            id="help",
        ),
        pytest.param(
            {
                "text": "/bind CMD-12345",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
            None,
            ParsedCommand(
                kind=CommandKind.BIND,
                raw_text="/bind CMD-12345",
                args="CMD-12345",
                mentions=(),
                validation_error=None,
            ),
            id="bind",
        ),
        pytest.param(
            {
                "text": "/link LINK-99999",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
            None,
            ParsedCommand(
                kind=CommandKind.LINK,
                raw_text="/link LINK-99999",
                args="LINK-99999",
                mentions=(),
                validation_error=None,
            ),
            id="link",
        ),
        pytest.param(
            {"text": "/whoami", "entities": [{"type": "bot_command", "offset": 0, "length": 7}]},
            None,
            ParsedCommand(
                kind=CommandKind.WHOAMI,
                raw_text="/whoami",
                args="",
                mentions=(),
                validation_error=None,
            ),
            id="whoami",
        ),
        pytest.param(
            {
                "text": "/task @alice Chuẩn bị báo cáo tuần",
                "entities": [
                    {"type": "bot_command", "offset": 0, "length": 5},
                    {"type": "mention", "offset": 6, "length": 6},
                ],
            },
            None,
            ParsedCommand(
                kind=CommandKind.TASK,
                raw_text="/task @alice Chuẩn bị báo cáo tuần",
                args="Chuẩn bị báo cáo tuần",
                mentions=(MentionTarget(username="alice", user_id=None),),
                validation_error=None,
            ),
            id="task-with-mention",
        ),
        pytest.param(
            {
                "text": "/task Báo cáo cuối tháng",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
            None,
            ParsedCommand(
                kind=CommandKind.TASK,
                raw_text="/task Báo cáo cuối tháng",
                args="Báo cáo cuối tháng",
                mentions=(),
                validation_error=None,
            ),
            id="task-no-mention",
        ),
        pytest.param(
            {
                "text": "/assign @bob 7c5e...",
                "entities": [
                    {"type": "bot_command", "offset": 0, "length": 7},
                    {"type": "mention", "offset": 8, "length": 4},
                ],
            },
            None,
            ParsedCommand(
                kind=CommandKind.ASSIGN,
                raw_text="/assign @bob 7c5e...",
                args="7c5e...",
                mentions=(MentionTarget(username="bob", user_id=None),),
                validation_error=None,
            ),
            id="assign",
        ),
        pytest.param(
            {"text": "/mytasks", "entities": [{"type": "bot_command", "offset": 0, "length": 8}]},
            None,
            ParsedCommand(
                kind=CommandKind.MYTASKS,
                raw_text="/mytasks",
                args="",
                mentions=(),
                validation_error=None,
            ),
            id="mytasks",
        ),
        pytest.param(
            {"text": "/done 7c5e...", "entities": [{"type": "bot_command", "offset": 0, "length": 5}]},
            None,
            ParsedCommand(
                kind=CommandKind.DONE,
                raw_text="/done 7c5e...",
                args="7c5e...",
                mentions=(),
                validation_error=None,
            ),
            id="done",
        ),
    ],
)
def test_parse_message_happy_paths(
    message: Mapping[str, object],
    bot_username: str | None,
    expected: ParsedCommand,
) -> None:
    assert parse_message(message, bot_username=bot_username) == expected


@pytest.mark.parametrize(
    (
        "message",
        "bot_username",
        "expected_kind",
        "expected_args",
        "expected_mentions",
        "expected_validation_error",
    ),
    [
        pytest.param(
            {
                "text": "/task@CMDSupportBot @alice Test",
                "entities": [
                    {"type": "bot_command", "offset": 0, "length": 19},
                    {"type": "mention", "offset": 20, "length": 6},
                ],
            },
            "CMDSupportBot",
            CommandKind.TASK,
            "Test",
            (MentionTarget(username="alice", user_id=None),),
            None,
            id="bot-mention-suffix",
        ),
        pytest.param(
            {
                "text": "/assign @bob Tôi giúp",
                "entities": [
                    {"type": "bot_command", "offset": 0, "length": 7},
                    {"type": "mention", "offset": 8, "length": 4},
                    {
                        "type": "text_mention",
                        "offset": 13,
                        "length": 3,
                        "user": {"id": 987654321, "username": "helper"},
                    },
                ],
            },
            None,
            CommandKind.ASSIGN,
            "Tôi giúp",
            (
                MentionTarget(username="bob", user_id=None),
                MentionTarget(username=None, user_id=987654321),
            ),
            None,
            id="text-mention-user-id",
        ),
        pytest.param(
            {"text": "Alice làm giúp báo cáo nhé", "entities": []},
            None,
            CommandKind.NO_COMMAND,
            "Alice làm giúp báo cáo nhé",
            (),
            None,
            id="plain-text",
        ),
        pytest.param(
            {"text": "/foobar", "entities": [{"type": "bot_command", "offset": 0, "length": 7}]},
            None,
            CommandKind.UNKNOWN,
            "",
            (),
            None,
            id="unknown-command",
        ),
        pytest.param(
            {"text": "/task", "entities": [{"type": "bot_command", "offset": 0, "length": 5}]},
            None,
            CommandKind.TASK,
            "",
            (),
            "Task title is required.",
            id="task-missing-title",
        ),
        pytest.param(
            {"text": "/assign Test", "entities": [{"type": "bot_command", "offset": 0, "length": 7}]},
            None,
            CommandKind.ASSIGN,
            "Test",
            (),
            "Assignee mention is required.",
            id="assign-missing-mention",
        ),
        pytest.param(
            {"text": "/bind", "entities": [{"type": "bot_command", "offset": 0, "length": 5}]},
            None,
            CommandKind.BIND,
            "",
            (),
            "Code is required after the command.",
            id="bind-missing-code",
        ),
        pytest.param(
            {"text": "   ", "entities": []},
            None,
            CommandKind.NO_COMMAND,
            "",
            (),
            None,
            id="whitespace-only",
        ),
        pytest.param(
            {"text": "/task something", "entities": []},
            None,
            CommandKind.TASK,
            "something",
            (),
            None,
            id="fallback-without-entities",
        ),
        pytest.param(
            {"text": "", "entities": []},
            None,
            CommandKind.NO_COMMAND,
            "",
            (),
            None,
            id="empty-text",
        ),
    ],
)
def test_parse_message_edge_cases(
    message: Mapping[str, object],
    bot_username: str | None,
    expected_kind: CommandKind,
    expected_args: str,
    expected_mentions: tuple[MentionTarget, ...],
    expected_validation_error: str | None,
) -> None:

    parsed = parse_message(message, bot_username=bot_username)

    assert parsed.kind == expected_kind
    assert parsed.args == expected_args
    assert parsed.mentions == expected_mentions
    assert parsed.validation_error == expected_validation_error
    if expected_kind is CommandKind.NO_COMMAND:
        assert parsed.raw_text == expected_args
    else:
        assert parsed.raw_text == message.get("text", "")
