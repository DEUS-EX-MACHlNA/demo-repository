"""
app/schemas/enums.py
모든 Enum 정의 통합
"""
from enum import Enum


class NPCStatus(str, Enum):
    """NPC 상태"""
    ALIVE = "alive"
    DECEASED = "deceased"
    MISSING = "missing"
    UNKNOWN = "unknown"


class Intent(str, Enum):
    """파싱된 의도 타입"""
    LEADING = "leading"
    NEUTRAL = "neutral"
    EMPATHIC = "empathic"
    SUMMARIZE = "summarize"
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    """사용 가능한 Tool 이름"""
    NPC_TALK = "npc_talk"
    ACTION = "action"
    ITEM_USAGE = "item_usage"
