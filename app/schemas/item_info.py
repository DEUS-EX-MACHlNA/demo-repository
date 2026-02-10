"""
app/schemas/item.py
아이템 관련 스키마
"""
from typing import List, Dict, Any

from pydantic import BaseModel, Field


class ItemSchema(BaseModel):
    """아이템 정의"""
    item_id: str = Field(..., description="아이템 고유 ID")
    name: str = Field(..., description="아이템 이름")
    type: str = Field(..., description="아이템 타입")
    description: str = Field(..., description="아이템 설명")

    acquire: Dict[str, Any] = Field(..., description="획득 조건 로직 (구조 자유)")
    use: Dict[str, Any] = Field(..., description="사용 효과 및 행동 로직 (구조 자유)")


class ItemsCollectionSchema(BaseModel):
    """아이템 컬렉션"""
    items: List[ItemSchema] = Field(..., description="전체 아이템 리스트")
