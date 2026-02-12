"""
app/lock_manager.py
Lock Manager - locks.yaml 기반 정보 해금 시스템

매 턴 시작 전에 실행되어 조건을 충족한 정보를 해금합니다.
해금된 정보는 이후 턴에서 NPC 대화, 힌트 등에 활용됩니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from app.schemas import WorldStatePipeline
from app.schemas.lock import UnlockedInfo, LockCheckResult
from app.condition_eval import evaluate_condition

logger = logging.getLogger(__name__)

# 해금된 정보의 메모리 타입 및 중요도
MEMORY_TYPE_SECRET = "unlocked_secret"
SECRET_IMPORTANCE_SCORE = 9.5  # 매우 높은 중요도 (최대 10)


class LockManager:
    """
    정보 해금 관리자

    locks.yaml의 조건을 평가하고 해금된 정보를 추적합니다.
    """

    def __init__(self):
        self._unlocked_ids: Set[str] = set()  # 해금된 info_id 집합

    def check_unlocks(
        self,
        world_state: WorldStatePipeline,
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
            # if info_id in self._unlocked_ids:
            #     continue
            if world_state.locks[info_id]:
                continue

            # 조건 평가 (공용 ConditionEvaluator 사용)
            condition = lock.get("unlock_condition", "")
            if evaluate_condition(condition, world_state):
                # 해금!
                self._unlocked_ids.add(info_id)

                # NEW! 해금 여부 저장
                world_state.locks[info_id] = True
                
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
        world_state: WorldStatePipeline,
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
            add_memory(npc_state.memory, memory_entry)
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


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import logging
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldStatePipeline

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("LOCK MANAGER 테스트")
    print("=" * 60)

    # 시나리오 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오: {assets.scenario.get('title')}")

    # locks.yaml 확인
    locks_data = assets.extras.get("locks", {})
    locks = locks_data.get("locks", [])
    print(f"\n[2] 정의된 Lock ({len(locks)}개):")
    for i, lock in enumerate(locks, 1):
        print(f"  {i}. {lock.get('info_id')}: {lock.get('info_title')}")
        print(f"     조건: {lock.get('unlock_condition')}")
        print(f"     접근 가능 NPC: {lock.get('access', {}).get('allowed_npcs', [])}")

    # LockManager 생성
    manager = LockManager()

    # 테스트 케이스 1: 초기 상태 (lock 미해금)
    print(f"\n[3] 테스트 1: 초기 상태 (조건 미충족)")
    print("-" * 60)

    world1 = WorldStatePipeline(
        turn=1,
        npcs={
            "brother": NPCState(
                npc_id="brother",
                stats={"affection": 30, "humanity": 50, "suspicion": 2}
            ),
            "stepfather": NPCState(
                npc_id="stepfather",
                stats={"affection": 10, "humanity": 20, "suspicion": 3}
            ),
        },
        vars={"humanity": 80, "suspicion_level": 5, "day": 1, "truth_revealed": False, "clue_count": 0},
        inventory=[],
    )

    result1 = manager.check_unlocks(world1, locks_data)
    print(f"  새로 해금된 정보: {len(result1.newly_unlocked)}개")
    for info in result1.newly_unlocked:
        print(f"    - {info.info_id}: {info.info_title}")
        print(f"      설명: {info.description}")
    print(f"  전체 해금된 정보 수: {len(result1.all_unlocked_ids)}")

    # 테스트 케이스 2: 조건 충족 - br_00_01 (npc.brother.affection >= 70)
    print(f"\n[4] 테스트 2: 동생 호감도 높음 (brother.affection >= 70)")
    print("-" * 60)

    world2 = WorldStatePipeline(
        turn=5,
        npcs={
            "brother": NPCState(
                npc_id="brother",
                stats={"affection": 75, "humanity": 60, "suspicion": 3},
                memory={"memory_stream": []},
            ),
            "stepfather": NPCState(
                npc_id="stepfather",
                stats={"affection": 20, "humanity": 30, "suspicion": 5},
                memory={"memory_stream": []},
            ),
        },
        vars={"humanity": 70, "suspicion_level": 20, "day": 2, "truth_revealed": False},
        inventory=[],
    )

    result2 = manager.check_unlocks(world2, locks_data)
    print(f"  새로 해금된 정보: {len(result2.newly_unlocked)}개")
    for info in result2.newly_unlocked:
        print(f"    - {info.info_id}: {info.info_title}")
        print(f"      설명: {info.description[:60]}...")
        print(f"      접근 가능 NPC: {info.allowed_npcs}")
    print(f"  전체 해금된 정보 수: {len(result2.all_unlocked_ids)}")
    print(f"  트리거된 이벤트: {result2.triggered_events}")

    # 메모리 주입 확인
    print(f"\n[5] NPC 메모리 확인:")
    for npc_id, npc_state in world2.npcs.items():
        memory_stream = npc_state.memory.get("memory_stream", [])
        print(f"  {npc_id}: {len(memory_stream)}개 메모리")
        for mem in memory_stream[-3:]:  # 최근 3개만
            print(f"    - [{mem.get('memory_type')}] {mem.get('description', '')[:40]}...")

    # 테스트 케이스 3: 여러 조건 동시 충족
    print(f"\n[6] 테스트 3: 복합 조건 충족 (humanity 낮음 + suspicion 높음 + day >= 4)")
    print("-" * 60)

    world3 = WorldStatePipeline(
        turn=35,
        npcs={
            "brother": NPCState(
                npc_id="brother",
                stats={"affection": 75, "humanity": 80, "suspicion": 5},
                memory={"memory_stream": []},
            ),
            "grandmother": NPCState(
                npc_id="grandmother",
                stats={"affection": 50, "humanity": 60, "suspicion": 8},
                memory={"memory_stream": []},
            ),
            "stepmother": NPCState(
                npc_id="stepmother",
                stats={"affection": 10, "humanity": 20, "suspicion": 9},
                memory={"memory_stream": []},
            ),
        },
        vars={"humanity": 25, "suspicion_level": 35, "day": 4, "truth_revealed": True, "clue_count": 2},
        inventory=["real_family_photo"],
    )

    result3 = manager.check_unlocks(world3, locks_data)
    print(f"  새로 해금된 정보: {len(result3.newly_unlocked)}개")
    for info in result3.newly_unlocked:
        print(f"    - {info.info_id}: {info.info_title}")
        print(f"      설명: {info.description[:60]}...")
    print(f"  전체 해금된 정보 수: {len(result3.all_unlocked_ids)}")
    print(f"  트리거된 이벤트: {result3.triggered_events}")

    # 테스트 케이스 4: 중복 체크 (이미 해금된 정보)
    print(f"\n[7] 테스트 4: 중복 체크 (같은 조건 재실행)")
    print("-" * 60)

    result4 = manager.check_unlocks(world3, locks_data)
    print(f"  새로 해금된 정보: {len(result4.newly_unlocked)}개 (중복 방지)")
    print(f"  전체 해금된 정보 수: {len(result4.all_unlocked_ids)}")

    # 특정 NPC가 접근 가능한 정보 조회
    print(f"\n[8] NPC별 접근 가능 정보:")
    for npc_id in world3.npcs.keys():
        accessible = manager.get_unlocked_info_for_npc(npc_id, locks_data)
        print(f"  {npc_id}: {len(accessible)}개")
        for info in accessible:
            print(f"    - {info.info_id}: {info.info_title}")

    print("\n" + "=" * 60)
    print("LOCK MANAGER 테스트 완료")
    print("=" * 60)
