from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import cast

TelegramEntity = dict[str, object]


class CommandKind(str, Enum):
    HELP = "help"
    BIND = "bind"
    LINK = "link"
    WHOAMI = "whoami"
    TASK = "task"
    ASSIGN = "assign"
    MYTASKS = "mytasks"
    DONE = "done"
    NO_COMMAND = "no_command"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MentionTarget:
    username: str | None
    user_id: int | None


@dataclass(frozen=True)
class ParsedCommand:
    kind: CommandKind
    raw_text: str
    args: str
    mentions: tuple[MentionTarget, ...]
    validation_error: str | None


_SUPPORTED_COMMANDS: dict[str, CommandKind] = {
    CommandKind.HELP.value: CommandKind.HELP,
    CommandKind.BIND.value: CommandKind.BIND,
    CommandKind.LINK.value: CommandKind.LINK,
    CommandKind.WHOAMI.value: CommandKind.WHOAMI,
    CommandKind.TASK.value: CommandKind.TASK,
    CommandKind.ASSIGN.value: CommandKind.ASSIGN,
    CommandKind.MYTASKS.value: CommandKind.MYTASKS,
    CommandKind.DONE.value: CommandKind.DONE,
}


def parse_message(message: Mapping[str, object], bot_username: str | None = None) -> ParsedCommand:
    raw_text = _coerce_text(message.get("text", ""))
    if not raw_text.strip():
        return ParsedCommand(
            kind=CommandKind.NO_COMMAND,
            raw_text="",
            args="",
            mentions=(),
            validation_error=None,
        )

    entities = _coerce_entities(message.get("entities", []))
    command_data = _extract_command_data(raw_text, entities, bot_username)
    if command_data is None:
        return ParsedCommand(
            kind=CommandKind.NO_COMMAND,
            raw_text=raw_text,
            args="",
            mentions=(),
            validation_error=None,
        )

    command_name, body_start = command_data
    kind = _SUPPORTED_COMMANDS.get(command_name.casefold(), CommandKind.UNKNOWN)
    mentions, first_mention = _extract_mentions(entities, raw_text)
    args = _extract_args(raw_text, body_start, kind, first_mention)
    validation_error = _validation_error(kind, args, mentions)

    return ParsedCommand(
        kind=kind,
        raw_text=raw_text,
        args=args,
        mentions=mentions,
        validation_error=validation_error,
    )


def _coerce_text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _coerce_entities(value: object) -> list[TelegramEntity]:
    if not isinstance(value, list):
        return []

    entities: list[TelegramEntity] = []
    for entity in cast(list[object], value):
        if isinstance(entity, dict):
            entities.append(cast(TelegramEntity, entity))
    return entities


def _extract_command_data(
    text: str,
    entities: Sequence[TelegramEntity],
    bot_username: str | None,
) -> tuple[str, int] | None:
    command_entity = _first_bot_command_entity(entities)
    if command_entity is not None:
        offset = _get_int(command_entity, "offset", default=-1)
        if offset == 0:
            length = max(_get_int(command_entity, "length", default=0), 0)
            raw_command = text[:length] if length > 0 else ""
            command_name = raw_command[1:] if raw_command.startswith("/") else raw_command.lstrip("/")
            command_name = _strip_bot_username(command_name, bot_username)
            return command_name, min(length, len(text))

    if not text.startswith("/"):
        return None

    raw_command = _first_token(text)
    command_name = _strip_bot_username(raw_command[1:], bot_username)
    return command_name, len(raw_command)


def _first_bot_command_entity(entities: Sequence[TelegramEntity]) -> TelegramEntity | None:
    for entity in entities:
        if _get_str(entity, "type") == "bot_command" and _get_int(entity, "offset", default=-1) == 0:
            return entity
    return None


def _first_token(text: str) -> str:
    if not text:
        return ""
    token, _, _ = text.partition(" ")
    return token


def _strip_bot_username(command_name: str, bot_username: str | None) -> str:
    if not bot_username or "@" not in command_name:
        return command_name

    base, suffix = command_name.split("@", 1)
    if suffix.casefold() == bot_username.casefold():
        return base
    return command_name


def _extract_mentions(
    entities: Sequence[TelegramEntity],
    text: str,
) -> tuple[tuple[MentionTarget, ...], TelegramEntity | None]:
    mentions: list[MentionTarget] = []
    first_mention: TelegramEntity | None = None

    ordered_entities = sorted(
        entities,
        key=lambda item: (_get_int(item, "offset", default=0), _get_int(item, "length", default=0)),
    )
    for entity in ordered_entities:
        entity_type = _get_str(entity, "type")
        if entity_type not in {"mention", "text_mention"}:
            continue

        if first_mention is None:
            first_mention = entity

        if entity_type == "mention":
            offset = _get_int(entity, "offset", default=0)
            length = max(_get_int(entity, "length", default=0), 0)
            mention_text = text[offset : offset + length]
            username = mention_text.removeprefix("@").casefold() or None
            mentions.append(MentionTarget(username=username, user_id=None))
            continue

        mentions.append(MentionTarget(username=None, user_id=_get_user_id(entity.get("user"))))

    return tuple(mentions), first_mention


def _extract_args(
    text: str,
    body_start: int,
    kind: CommandKind,
    first_mention: TelegramEntity | None,
) -> str:
    body_text = text[max(min(body_start, len(text)), 0) :]
    trimmed_body = body_text.strip()
    if kind not in {CommandKind.TASK, CommandKind.ASSIGN}:
        return trimmed_body

    if first_mention is None:
        return trimmed_body

    mention_offset = _get_int(first_mention, "offset", default=-1)
    mention_length = max(_get_int(first_mention, "length", default=0), 0)
    if mention_offset < body_start:
        return trimmed_body

    relative_start = mention_offset - body_start
    relative_end = relative_start + mention_length
    if relative_start > len(body_text):
        return trimmed_body

    remaining = body_text[:relative_start] + body_text[relative_end:]
    return remaining.strip()


def _validation_error(
    kind: CommandKind,
    args: str,
    mentions: tuple[MentionTarget, ...],
) -> str | None:
    if kind == CommandKind.TASK and not args:
        return "Task title is required."
    if kind == CommandKind.ASSIGN and not mentions:
        return "Assignee mention is required."
    if kind in {CommandKind.BIND, CommandKind.LINK} and not args:
        return "Code is required after the command."
    return None


def _get_int(mapping: Mapping[str, object], key: str, default: int) -> int:
    value = mapping.get(key)
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _get_str(mapping: Mapping[str, object], key: str, default: str = "") -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) else default


def _get_user_id(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None

    user = cast(Mapping[str, object], value)
    user_id = user.get("id")
    if isinstance(user_id, bool):
        return None
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str):
        try:
            return int(user_id)
        except ValueError:
            return None
    return None
