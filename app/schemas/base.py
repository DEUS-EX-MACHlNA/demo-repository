"""
app/schemas.py
Pydantic 스키마 정의 (검증 및 직렬화용)

WorldState 등의 데이터 구조를 Pydantic으로 검증할 수 있습니다.
FastAPI Response Model로도 사용 가능합니다.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# NPCState Schema
# ============================================================
class NPCStateSchema(BaseModel):
    """NPC 상태 스키마"""
    npc_id: str = Field(..., description="NPC 고유 ID")
    trust: int = Field(0, ge=0, le=100, description="신뢰도 (0~100)")
    fear: int = Field(0, ge=0, le=100, description="두려움 (0~100)")
    suspicion: int = Field(0, ge=0, le=100, description="의심 (0~100)")
    extras: Dict[str, Any] = Field(default_factory=dict, description="커스텀 필드")

    class Config:
        json_schema_extra = {
            "example": {
                "npc_id": "family",
                "trust": 25,
                "fear": 0,
                "suspicion": 5,
                "extras": {}
            }
        }


# ============================================================
# WorldState Schema
# ============================================================
class WorldStateSchema(BaseModel):
    """월드 상태 스키마"""
    turn: int = Field(1, ge=1, description="현재 턴 (1부터 시작)")
    npcs: Dict[str, NPCStateSchema] = Field(
        default_factory=dict,
        description="NPC 상태 맵 (npc_id → NPCState)"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="게임 플래그 (ending, act 등)"
    )
    inventory: List[str] = Field(
        default_factory=list,
        description="소유 아이템 ID 목록"
    )
    locks: Dict[str, bool] = Field(
        default_factory=dict,
        description="잠금/해금 상태"
    )
    vars: Dict[str, Any] = Field(
        default_factory=dict,
        description="시나리오 변수 (clue_count, identity_match_score 등)"
    )

    @field_validator('inventory')
    @classmethod
    def validate_inventory_no_duplicates(cls, v: List[str]) -> List[str]:
        """인벤토리 중복 제거 (선택적)"""
        # 중복 허용하려면 이 validator 제거
        return list(dict.fromkeys(v))  # 순서 유지하며 중복 제거

    class Config:
        json_schema_extra = {
            "example": {
                "turn": 5,
                "npcs": {
                    "family": {
                        "npc_id": "family",
                        "trust": 25,
                        "fear": 0,
                        "suspicion": 5,
                        "extras": {}
                    }
                },
                "flags": {
                    "ending": None,
                    "act": 2
                },
                "inventory": ["casefile_brief", "pattern_analyzer"],
                "locks": {
                    "fam_00_01.is_unlocked": True
                },
                "vars": {
                    "clue_count": 7,
                    "identity_match_score": 4,
                    "fabrication_score": 6
                }
            }
        }


# ============================================================
# GetState Request/Response
# ============================================================
class GetStateRequest(BaseModel):
    """get_state 요청 파라미터"""
    user_id: str = Field(..., description="사용자 ID", min_length=1)
    scenario_id: str = Field(..., description="시나리오 ID", min_length=1)
    # assets는 서버 내부에서 로드하므로 요청에 포함 안 됨

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "scenario_id": "culprit_ai"
            }
        }


class GetStateResponse(BaseModel):
    """get_state 응답"""
    user_id: str
    scenario_id: str
    state: WorldStateSchema

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_12345",
                "scenario_id": "culprit_ai",
                "state": {
                    "turn": 1,
                    "npcs": {},
                    "flags": {},
                    "inventory": [],
                    "locks": {},
                    "vars": {}
                }
            }
        }


# ============================================================
# Delta Schema (apply_delta 입력용)
# ============================================================
class StateDeltaSchema(BaseModel):
    """상태 델타 스키마"""
    npc_stats: Dict[str, Dict[str, int]] = Field(
        default_factory=dict,
        description="NPC 스탯 변화 {npc_id: {stat_name: delta}}"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict,
        description="플래그 변경"
    )
    inventory_add: List[str] = Field(
        default_factory=list,
        description="인벤토리에 추가할 아이템"
    )
    inventory_remove: List[str] = Field(
        default_factory=list,
        description="인벤토리에서 제거할 아이템"
    )
    locks: Dict[str, bool] = Field(
        default_factory=dict,
        description="잠금 상태 변경"
    )
    vars: Dict[str, Any] = Field(
        default_factory=dict,
        description="변수 변경 (숫자면 델타, 아니면 덮어쓰기)"
    )
    turn_increment: int = Field(
        0,
        ge=0,
        description="턴 증가량"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "npc_stats": {
                    "family": {
                        "trust": 2,
                        "fear": -1
                    }
                },
                "flags": {},
                "inventory_add": ["call_log"],
                "inventory_remove": [],
                "locks": {
                    "fam_00_01.is_unlocked": True
                },
                "vars": {
                    "clue_count": 1,
                    "identity_match_score": 1
                },
                "turn_increment": 1
            }
        }


# ============================================================
# Culprit AI 시나리오 특화 스키마
# ============================================================
class CulpritAIVars(BaseModel):
    """culprit_ai 시나리오 전용 변수"""
    clue_count: int = Field(0, ge=0, le=10, description="단서 개수")
    identity_match_score: int = Field(0, ge=0, le=10, description="자기 동일성 점수")
    fabrication_score: int = Field(0, ge=0, le=10, description="조작 점수")

    class Config:
        json_schema_extra = {
            "example": {
                "clue_count": 7,
                "identity_match_score": 4,
                "fabrication_score": 6
            }
        }


class CulpritAIFlags(BaseModel):
    """culprit_ai 시나리오 전용 플래그"""
    ending: Optional[str] = Field(
        None,
        description="엔딩 타입",
        pattern="^(self_confess|scapegoat|forced_shutdown)$"
    )
    act: Optional[int] = Field(None, ge=1, le=3, description="현재 막 (1~3)")

    class Config:
        json_schema_extra = {
            "example": {
                "ending": None,
                "act": 2
            }
        }


# ============================================================
# Utility: WorldState ↔ WorldStateSchema 변환
# ============================================================
def worldstate_to_schema(state: "WorldState") -> WorldStateSchema:
    """WorldState → WorldStateSchema 변환"""
    from app.models import WorldState

    return WorldStateSchema(
        turn=state.turn,
        npcs={
            npc_id: NPCStateSchema(
                npc_id=npc.npc_id,
                trust=npc.trust,
                fear=npc.fear,
                suspicion=npc.suspicion,
                extras=npc.extras
            )
            for npc_id, npc in state.npcs.items()
        },
        flags=state.flags.copy(),
        inventory=state.inventory.copy(),
        locks=state.locks.copy(),
        vars=state.vars.copy()
    )


def schema_to_worldstate(schema: WorldStateSchema) -> "WorldState":
    """WorldStateSchema → WorldState 변환"""
    from app.models import NPCState, WorldState

    return WorldState(
        turn=schema.turn,
        npcs={
            npc_id: NPCState(
                npc_id=npc_schema.npc_id,
                trust=npc_schema.trust,
                fear=npc_schema.fear,
                suspicion=npc_schema.suspicion,
                extras=npc_schema.extras
            )
            for npc_id, npc_schema in schema.npcs.items()
        },
        flags=dict(schema.flags),
        inventory=list(schema.inventory),
        locks=dict(schema.locks),
        vars=dict(schema.vars)
    )


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import json

    print("=" * 60)
    print("PYDANTIC SCHEMA 테스트")
    print("=" * 60)

    # WorldState 스키마 생성
    state = WorldStateSchema(
        turn=5,
        npcs={
            "family": NPCStateSchema(
                npc_id="family",
                trust=25,
                fear=0,
                suspicion=5
            )
        },
        flags={"ending": None, "act": 2},
        inventory=["casefile_brief", "pattern_analyzer"],
        locks={"fam_00_01.is_unlocked": True},
        vars={
            "clue_count": 7,
            "identity_match_score": 4,
            "fabrication_score": 6
        }
    )

    print("\n[1] WorldStateSchema 생성:")
    print(json.dumps(state.model_dump(), indent=2, ensure_ascii=False))

    # JSON 직렬화/역직렬화 테스트
    print("\n[2] JSON 직렬화:")
    json_str = state.model_dump_json(indent=2)
    print(json_str)

    print("\n[3] JSON 역직렬화:")
    state_from_json = WorldStateSchema.model_validate_json(json_str)
    print(f"turn={state_from_json.turn}, npcs={list(state_from_json.npcs.keys())}")

    # 검증 테스트 (범위 초과)
    print("\n[4] 검증 테스트 (trust=150, 범위 초과):")
    try:
        invalid_npc = NPCStateSchema(
            npc_id="test",
            trust=150,  # 100 초과
            fear=0,
            suspicion=0
        )
    except Exception as e:
        print(f"✅ 검증 실패 (예상됨): {e}")

    # Delta 스키마 테스트
    print("\n[5] StateDeltaSchema 테스트:")
    delta = StateDeltaSchema(
        npc_stats={"family": {"trust": 2}},
        vars={"clue_count": 1},
        turn_increment=1
    )
    print(json.dumps(delta.model_dump(), indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("✅ PYDANTIC SCHEMA 테스트 완료")
    print("=" * 60)
