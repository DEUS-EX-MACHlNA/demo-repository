"""
app/schemas/player.py
플레이어 관련 스키마
"""
import re
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

_INTENT_COND_RE = re.compile(r"intent\s*(==|!=)\s*['\"]([^'\"]+)['\"]")
_SYSTEM_TIME_COND_RE = re.compile(r"system\.time\s*(==|!=)\s*['\"]([^'\"]+)['\"]")


class PlayerMemoSchema(BaseModel):
    """플레이어 메모"""
    id: int = Field(..., description="메모 고유 ID")
    text: str = Field(..., description="메모 내용")
    created_at_turn: int = Field(..., description="메모가 작성된 턴")


class PlayerSchema(BaseModel):
    """플레이어 정보"""
    current_node: str = Field(..., default_factory="player_room", description="현재 위치하고 있는 스토리 노드 ID (예: act1_open)")

    def refresh_avaliable_nodes(
        self,
        story_graph: Dict[str, Any],
        world_state: "WorldStatePipeline",
        *,
        intent: Optional[str] = None,
        system_time: Optional[str] = None,
        turn_limit: int = 50,
    ) -> List[str]:
        nodes = story_graph.get("nodes") if story_graph else None
        if not nodes or not self.current_node:
            self.avaliable_nodes = []
            return self.avaliable_nodes

        connected_nodes = None
        current_node = self.current_node
        for node in nodes:
            if node.get("node_id") == current_node:
                connected_nodes = node.get("connected_nodes") or []
                break

        if not connected_nodes:
            self.avaliable_nodes = []
            return self.avaliable_nodes

        if intent is None:
            intent = (world_state.vars or {}).get("intent") or (world_state.flags or {}).get("intent")
        if system_time is None:
            system_time = (world_state.vars or {}).get("system_time") or (world_state.vars or {}).get("time")

        from app.condition_eval import get_condition_evaluator
        from app.schemas.condition import EvalContext

        evaluator = get_condition_evaluator()
        context = EvalContext(world_state=world_state, turn_limit=turn_limit)

        def eval_condition(condition: str) -> bool:
            if not condition:
                return False
            condition = condition.strip()
            if condition == "true":
                return True
            if condition == "false":
                return False
            if "intent" not in condition and "system.time" not in condition:
                return evaluator.evaluate(condition, context)
            if " or " in condition:
                return any(eval_condition(part) for part in condition.split(" or "))
            if " and " in condition:
                return all(eval_condition(part) for part in condition.split(" and "))
            intent_match = _INTENT_COND_RE.match(condition)
            if intent_match:
                if intent is None:
                    return False
                op = intent_match.group(1)
                expected = intent_match.group(2)
                return (intent == expected) if op == "==" else (intent != expected)
            time_match = _SYSTEM_TIME_COND_RE.match(condition)
            if time_match:
                if system_time is None:
                    return False
                op = time_match.group(1)
                expected = time_match.group(2)
                return (system_time == expected) if op == "==" else (system_time != expected)
            return False

        available: List[str] = []
        seen: set[str] = set()
        for edge in connected_nodes:
            if not isinstance(edge, dict):
                continue
            next_node_id = edge.get("next_node_id")
            if not next_node_id or next_node_id in seen:
                continue
            condition = edge.get("condition", "")
            if condition in ("", "true"):
                available.append(next_node_id)
                seen.add(next_node_id)
                continue
            if condition == "false":
                continue
            if eval_condition(condition):
                available.append(next_node_id)
                seen.add(next_node_id)

        self.avaliable_nodes = available
        return available
    avaliable_nodes: List[str] = Field(default_factory=list, description="현재 접근 가능한 노드 ID 리스트")

    inventory: List[str] = Field(
        default_factory=list,
        description="소지하고 있는 아이템 ID 리스트 (예: ['casefile_brief', ...])"
    )

    memo: List[PlayerMemoSchema] = Field(
        default_factory=list,
        description="플레이어의 수첩(메모) 기록 목록"
    )
    # 여기 안에 humanity를 넣기
    stats: Dict[str, Any] = Field(default_factory=dict, description="플레이어의 현재 상황")

    memory: List[Dict[str, Any]] = Field(default_factory=list, description="LLM용 기억 데이터")
