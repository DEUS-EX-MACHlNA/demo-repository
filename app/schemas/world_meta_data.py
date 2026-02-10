from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.schemas.item_info import ItemsCollectionSchema


# [NEW] 현재 게임의 동적 상태 (The Scoreboard)
# =========================================================
class CurrentStateSchema(BaseModel):
    # 1. 시스템 상태
    turn: int = Field(..., description="현재 턴")
    date: str = Field(..., description="현재 날짜")

    # 2. 변수와 플래그 (가장 중요!)
    # 여기는 값이 계속 변하므로 Dict[str, Any]로 유연하게 받습니다.
    vars: Dict[str, int] = Field(
        default_factory=dict, 
        description="현재 변수 값 (예: {'clue_count': 3, 'trust': 10})"
    )
    flags: Dict[str, Any] = Field(
        default_factory=dict, 
        description="현재 플래그 상태 (예: {'met_boss': True})"
    )

# =========================================================
# 1. [Extras & Locks] 잠금 정보
#    - ID와 텍스트는 UI 표시에 필수적이므로 명시
#    - 해금 조건(logic)은 복잡하므로 Dict로 처리
# =========================================================
class LockSchema(BaseModel):
    # 1. [UI 표시용] 필수 필드
    info_id: str = Field(..., description="정보 ID")
    info_title: str = Field(..., description="제목")
    description: str = Field(..., description="내용")
    is_unlocked: bool = Field(default=False, description="해금 여부")
    
    # 2. [Logic] 게임 로직용 핵심 필드 (최상위로 꺼냄)
    # 딕셔너리(logic) 안에 숨기지 않고 바로 접근 가능하게 만듭니다.
    linked_info_id: Optional[str] = Field(None, description="연결된 정보 ID")
    unlock_condition: Optional[str] = Field(None, description="해금 조건식")
    reveal_trigger: Optional[str] = Field(None, description="해금 트리거")
    
    # 3. [Complex] 구조가 복잡한 Access는 Dict로 퉁치기
    # 요청하신 대로 access는 별도 클래스 정의 없이 딕셔너리로 받습니다.
    access: Optional[Dict[str, Any]] = Field(
        default_factory=dict, 
        description="접근 권한 설정 (예: {'allowed_npcs': ['partner']})"
    )

    # 4. [Safety] 나중에 'icon', 'sound' 같은 잡다한 게 추가돼도 터지지 않게 설정
    class Config:
        extra = "allow" 

class LocksSchemaList(BaseModel):
    # JSON 구조가 {"locks": [...]} 형태
    locks: List[LockSchema]

# =========================================================
# 3. [Scenario] 시나리오 메타 & 룰
#    - 제목, 장르 등 메타데이터는 엄격하게
#    - 엔딩 조건이나 초기 상태값(State Schema)은 유연하게
# =========================================================
class EndingSchema(BaseModel):
    # [Strict] 엔딩 식별용
    ending_id: str
    name: str
    epilogue_prompt: str


class ScenarioSchema(BaseModel):
    # [Strict] 규칙 (텍스트 리스트라 구조가 단순함)
    global_rules: List[str]
    victory_conditions: List[str]
    failure_conditions: List[str]
    
    # [Flexible] 엔딩과 상태 설정
    endings: List[EndingSchema]


# =========================================================
# 👑 [ROOT] World Data Schema
# =========================================================
class WorldDataSchema(BaseModel):
    state: CurrentStateSchema
    scenario: ScenarioSchema
    locks: LocksSchemaList
    items: ItemsCollectionSchema # 이미 만들어둔 실용 버전 스키마 사용