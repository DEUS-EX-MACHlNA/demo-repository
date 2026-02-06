"""
app/lock_manager.py
Lock Manager - locks.yaml 기반 정보 해금 시스템

매 턴 시작 전에 실행되어 조건을 충족한 정보를 해금합니다.
해금된 정보는 이후 턴에서 NPC 대화, 힌트 등에 활용됩니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.models import WorldState
from app.condition_eval import evaluate_condition

logger = logging.getLogger(__name__)

# 해금된 정보의 메모리 타입 및 중요도
MEMORY_TYPE_SECRET = "unlocked_secret"
SECRET_IMPORTANCE_SCORE = 9.5  # 매우 높은 중요도 (최대 10)


@dataclass
class UnlockedInfo:
    """해금된 정보"""
    info_id: str
    info_title: str
    description: str
    reveal_trigger: str
    linked_info_id: Optional[str] = None
    allowed_npcs: List[str] = field(default_factory=list)


@dataclass
class LockCheckResult:
    """Lock 체크 결과"""
    newly_unlocked: List[UnlockedInfo]  # 이번 턴에 새로 해금된 정보
    all_unlocked_ids: Set[str]  # 현재까지 해금된 모든 정보 ID
    triggered_events: List[str]  # 발생해야 할 reveal_trigger 이벤트


class LockManager:
    """
    정보 해금 관리자

    locks.yaml의 조건을 평가하고 해금된 정보를 추적합니다.
    """

    def __init__(self):
        self._unlocked_ids: Set[str] = set()  # 해금된 info_id 집합

    def check_unlocks(
        self,
        world_state: WorldState,
        locks_data: Dict[str, Any],
    ) -> LockCheckResult:
        """
        모든 lock의 unlock_condition을 체크하고 새로 해금된 정보를 반환합니다.

        Args:
            world_state: 현재 월드 상태
            locks_data: locks.yaml 내용 (assets.extras.get("locks", {}))

        Returns:
            LockCheckResult: 해금 결과
        """
        newly_unlocked: List[UnlockedInfo] = []
        triggered_events: List[str] = []

        locks = locks_data.get("locks", [])

        for lock in locks:
            info_id = lock.get("info_id", "")

            # 이미 해금된 건 스킵
            if info_id in self._unlocked_ids:
                continue

            # 조건 평가 (공용 ConditionEvaluator 사용)
            condition = lock.get("unlock_condition", "")
            if evaluate_condition(condition, world_state):
                # 해금!
                self._unlocked_ids.add(info_id)

                unlocked_info = UnlockedInfo(
                    info_id=info_id,
                    info_title=lock.get("info_title", ""),
                    description=lock.get("description", ""),
                    reveal_trigger=lock.get("reveal_trigger", ""),
                    linked_info_id=lock.get("linked_info_id"),
                    allowed_npcs=lock.get("access", {}).get("allowed_npcs", []),
                )
                newly_unlocked.append(unlocked_info)

                if unlocked_info.reveal_trigger:
                    triggered_events.append(unlocked_info.reveal_trigger)

                logger.info(f"[LockManager] 정보 해금: {info_id} - {unlocked_info.info_title}")

                # 해금 즉시 해당 NPC 메모리에 주입 (높은 중요도)
                self._inject_to_npc_memory(unlocked_info, world_state)

        return LockCheckResult(
            newly_unlocked=newly_unlocked,
            all_unlocked_ids=self._unlocked_ids.copy(),
            triggered_events=triggered_events,
        )

    def get_unlocked_info_for_npc(
        self,
        npc_id: str,
        locks_data: Dict[str, Any],
    ) -> List[UnlockedInfo]:
        """
        특정 NPC가 접근 가능한 해금된 정보 목록을 반환합니다.

        Args:
            npc_id: NPC ID
            locks_data: locks.yaml 내용

        Returns:
            해당 NPC가 알고 있는 정보 목록
        """
        result = []
        locks = locks_data.get("locks", [])

        for lock in locks:
            info_id = lock.get("info_id", "")
            if info_id not in self._unlocked_ids:
                continue

            allowed_npcs = lock.get("access", {}).get("allowed_npcs", [])
            if npc_id in allowed_npcs:
                result.append(UnlockedInfo(
                    info_id=info_id,
                    info_title=lock.get("info_title", ""),
                    description=lock.get("description", ""),
                    reveal_trigger=lock.get("reveal_trigger", ""),
                    linked_info_id=lock.get("linked_info_id"),
                    allowed_npcs=allowed_npcs,
                ))

        return result

    def is_unlocked(self, info_id: str) -> bool:
        """특정 정보가 해금되었는지 확인"""
        return info_id in self._unlocked_ids

    def get_all_unlocked_ids(self) -> Set[str]:
        """해금된 모든 정보 ID 반환"""
        return self._unlocked_ids.copy()

    def reset(self) -> None:
        """해금 상태 초기화 (새 게임 시작 시)"""
        self._unlocked_ids.clear()

    def load_state(self, unlocked_ids: Set[str]) -> None:
        """저장된 해금 상태 로드"""
        self._unlocked_ids = unlocked_ids.copy()

    def _inject_to_npc_memory(
        self,
        unlocked_info: UnlockedInfo,
        world_state: WorldState,
    ) -> List[str]:
        """
        해금된 정보를 해당 NPC들의 메모리에 즉시 추가합니다.
        check_unlocks() 내부에서 자동 호출됩니다.
        """
        from app.agents.memory import MemoryEntry, add_memory

        injected_npcs = []

        for npc_id in unlocked_info.allowed_npcs:
            npc_state = world_state.npcs.get(npc_id)
            if not npc_state:
                logger.warning(f"[LockManager] NPC를 찾을 수 없음: {npc_id}")
                continue

            # 메모리 생성: 높은 중요도로 설정
            memory_entry = MemoryEntry.create(
                npc_id=npc_id,
                description=f"[비밀 발각] {unlocked_info.info_title}: {unlocked_info.description}",
                importance_score=SECRET_IMPORTANCE_SCORE,
                current_turn=world_state.turn,
                memory_type=MEMORY_TYPE_SECRET,
                metadata={
                    "info_id": unlocked_info.info_id,
                    "reveal_trigger": unlocked_info.reveal_trigger,
                    "linked_info_id": unlocked_info.linked_info_id,
                },
            )

            # NPC의 메모리 스트림에 추가
            add_memory(npc_state.extras, memory_entry)
            injected_npcs.append(npc_id)

            logger.info(
                f"[LockManager] 메모리 주입: {npc_id} <- {unlocked_info.info_title} "
                f"(importance={SECRET_IMPORTANCE_SCORE})"
            )

        return injected_npcs


# ============================================================
# 싱글턴
# ============================================================
_lock_manager_instance: Optional[LockManager] = None


def get_lock_manager() -> LockManager:
    """LockManager 싱글턴 인스턴스 반환"""
    global _lock_manager_instance
    if _lock_manager_instance is None:
        _lock_manager_instance = LockManager()
    return _lock_manager_instance
