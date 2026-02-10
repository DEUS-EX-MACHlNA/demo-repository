from typing import List, Dict, Any
from pydantic import BaseModel, Field

class ItemSchema(BaseModel):
    # 1. [Strict] 프론트엔드/기획에서 절대 변하면 안 되는 핵심 필드
    item_id: str = Field(..., description="아이템 고유 ID")
    name: str = Field(..., description="아이템 이름")
    type: str = Field(..., description="아이템 타입")
    description: str = Field(..., description="아이템 설명")

    # 2. [Flexible] 기획 변경이 잦은 로직은 'dict'로 유연하게 처리
    # - acquire 안에 method가 있든 condition이 있든 신경 안 씀 (에러 안 남)
    # - use 안에 actions가 추가되든 effects가 바뀌든 코드 수정 불필요
    acquire: Dict[str, Any] = Field(..., description="획득 조건 로직 (구조 자유)")
    use: Dict[str, Any] = Field(..., description="사용 효과 및 행동 로직 (구조 자유)")

    # 3. [Flexible] 그 외 처리해야 할 놈들 어쩌면 TODO일 수 있읍니다
    # 사용 여부, 상태
    used : bool = Field(False, description="아이템 사용 여부")
    # 얜 있을 수도 없을 수도 있습니다
    state : str = Field("", description="아이템 상태")
    # 아이템의 위치
    location : str = Field("", description="아이템 위치")

class ItemsCollectionSchema(BaseModel):
    # 최상위 리스트 구조는 유지
    items: List[ItemSchema] = Field(..., description="전체 아이템 리스트")