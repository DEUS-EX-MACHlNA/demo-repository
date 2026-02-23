"""
app/schemas/status.py
모든 Enum 정의 통합
"""
from enum import Enum


class NPCStatus(str, Enum):
    """NPC 상태"""
    ALIVE = "alive"
    MISSING = "missing"
    SLEEPING = "sleeping"

class GameStatus(str, Enum):
    """게임 상태"""
    LIVE = "live"        # 진행 중
    ENDING = "ending"    # 종료됨

class ItemStatus(str, Enum):
    """아이템 상태"""
    NOT_ACQUIRED = "not_acquired"
    ACQUIRED = "acquired"
    USED = "used"

class Intent(str, Enum):
    """파싱된 의도 타입"""
    INVESTIGATE = "investigate"
    OBEY = "obey"
    REBEL = "rebel"
    REVEAL = "reveal"
    SUMMARIZE = "summarize"
    NEUTRAL = "neutral"


class ToolName(str, Enum):
    """사용 가능한 Tool 이름"""
    NPC_TALK = "npc_talk"
    ACTION = "action"
    ITEM_USAGE = "item_usage"


class NpcId(str, Enum):
    """NPC 식별자"""
    STEPMOTHER = "stepmother"
    STEPFATHER = "stepfather"
    BROTHER = "brother"
    DOG_BARON = "dog_baron"
    GRANDMOTHER = "grandmother"

class ChatAt(str, Enum):
    """채팅 턴"""
    DAY = "day"
    NIGHT = "night"

class LogType(str, Enum):
    NARRATIVE = "narrative"       # 일반 서술 (행동 결과 등)
    DIALOGUE = "dialogue"         # 1:1 대화
    SYSTEM = "system"             # 시스템 메시지 (아이템 획득, 턴 경과)
    NIGHT_EVENT = "night_event"   # 야간 대화 (스크립트 형태)
    ERROR = "error"               # 에러 메시지