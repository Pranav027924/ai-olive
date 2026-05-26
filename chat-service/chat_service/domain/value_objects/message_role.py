"""MessageRole — who authored a message.

Matches the CHECK constraint on ``chat.messages.role`` (PRD §8.1).
"""

from __future__ import annotations

from enum import StrEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
