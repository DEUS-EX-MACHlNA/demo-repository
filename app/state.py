"""
app/state.py
World State Manager

월드 상태의 조회, 델타 적용, 영속화를 담당합니다.
현재는 in-memory 저장소로 구현되어 있으며, 추후 Redis/DB로 교체 가능합니다.

NPCState가 stats Dict 기반으로 변경됨.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from app.loader import ScenarioAssets
from app.schemas import NPCState, StateDelta, WorldState

logger = logging.getLogger(__name__)


# ============================================================
# In-Memory 저장소 (추후 Redis/DB로 교체 가능)
# ============================================================
class InMemoryStateStore:
    """인메모리 상태 저장소"""

    def __init__(self):
        # {(user_id, scenario_id): WorldState}
        self._store: dict[tuple[str, str], WorldState] = {}
        self._debug_log: list[dict[str, Any]] = []

    def get(self, user_id: str, scenario_id: str) -> Optional[WorldState]:
        """상태 조회"""
        key = (user_id, scenario_id)
        return copy.deepcopy(self._store.get(key))

    def set(self, user_id: str, scenario_id: str, state: WorldState):
        """상태 저장"""
        key = (user_id, scenario_id)
        self._store[key] = copy.deepcopy(state)

    def delete(self, user_id: str, scenario_id: str):
        """상태 삭제"""
        key = (user_id, scenario_id)
        self._store.pop(key, None)

    def exists(self, user_id: str, scenario_id: str) -> bool:
        """상태 존재 여부"""
        return (user_id, scenario_id) in self._store

    def clear_all(self):
        """모든 상태 삭제"""
        self._store.clear()

    def log_debug(self, entry: dict[str, Any]):
        """디버그 로그 기록"""
        self._debug_log.append(entry)
        # 최근 1000개만 유지
        if len(self._debug_log) > 1000:
            self._debug_log = self._debug_log[-1000:]

    def get_debug_log(self) -> list[dict[str, Any]]:
        """디버그 로그 조회"""
        return self._debug_log.copy()


# 전역 저장소 인스턴스
_store = InMemoryStateStore()


# ============================================================
# World State Manager
# ============================================================
class WorldStateManager:
    """
    월드 상태 관리자

    주요 책임:
    1. get_state: 유저/시나리오별 현재 상태 조회 (없으면 초기화)
    2. apply_delta: 상태에 델타 적용
    3. persist: 상태 영속화
    """

    def __init__(self, store: Optional[InMemoryStateStore] = None):
        self._store = store or _store

    def _create_initial_state(
        self,
        user_id: str,
        scenario_id: str,
        assets: ScenarioAssets
    ) -> WorldState:
        """시나리오 에셋 기반으로 초기 상태 생성"""

        # NPC 초기 상태 생성 (stats Dict 기반)
        npcs: dict[str, NPCState] = {}
        for npc_data in assets.npcs.get("npcs", []):
            npc_id = npc_data.get("npc_id")
            if npc_id:
                # 시나리오에서 정의된 stats 사용
                stats = npc_data.get("stats", {}).copy()
                memory = npc_data.get("memory", {}).copy()

                npcs[npc_id] = NPCState(
                    npc_id=npc_id,
                    stats=stats,
                    memory=memory,
                )

        # 초기 인벤토리
        initial_inventory = assets.get_initial_inventory()

        # 시나리오 스키마에서 초기 변수 로드
        state_schema = assets.get_state_schema()
        initial_vars = {}
        for var_name, var_spec in state_schema.get("vars", {}).items():
            initial_vars[var_name] = var_spec.get("default", 0)

        initial_flags = {}
        for flag_name, flag_spec in state_schema.get("flags", {}).items():
            initial_flags[flag_name] = flag_spec.get("default", None)

        state = WorldState(
            turn=1,
            npcs=npcs,
            flags=initial_flags,
            inventory=initial_inventory,
            locks={},
            vars=initial_vars
        )

        logger.info(
            f"Created initial state for user={user_id}, scenario={scenario_id}: "
            f"turn={state.turn}, npcs={len(state.npcs)}, inventory={len(state.inventory)}"
        )

        return state

    def get_state(
        self,
        user_id: str,
        scenario_id: str,
        assets: Optional[ScenarioAssets] = None
    ) -> WorldState:
        """
        유저/시나리오별 현재 상태 조회

        상태가 없으면 assets 기반으로 초기 상태를 생성합니다.

        Args:
            user_id: 유저 ID
            scenario_id: 시나리오 ID
            assets: 시나리오 에셋 (초기화 시 필요)

        Returns:
            WorldState: 현재 월드 상태
        """
        state = self._store.get(user_id, scenario_id)

        if state is None:
            if assets is None:
                # 에셋 없이는 기본 상태 생성
                logger.warning(f"No assets provided, creating minimal initial state")
                state = WorldState()
            else:
                state = self._create_initial_state(user_id, scenario_id, assets)
            self._store.set(user_id, scenario_id, state)

        return state

    def apply_delta(
        self,
        user_id: str,
        scenario_id: str,
        delta: dict[str, Any],
        assets: Optional[ScenarioAssets] = None
    ) -> WorldState:
        """
        상태에 델타 적용

        델타 규칙:
        - 숫자 스탯: +n 델타 지원, 0~100 클램프
        - bool/str: 덮어쓰기
        - list: append 또는 remove
        - unknown key: debug에 기록

        Args:
            user_id: 유저 ID
            scenario_id: 시나리오 ID
            delta: 적용할 델타 (StateDelta.to_dict() 형식)
            assets: 시나리오 에셋 (값 범위 검증용)

        Returns:
            WorldState: 델타 적용 후 상태
        """
        state = self.get_state(user_id, scenario_id, assets)
        debug_entries: list[dict[str, Any]] = []

        # StateDelta 형식으로 변환
        stat_delta = StateDelta.from_dict(delta)

        # 1. NPC 스탯 적용 (stats Dict 기반)
        for npc_id, stat_changes in stat_delta.npc_stats.items():
            if npc_id in state.npcs:
                npc = state.npcs[npc_id]
                for stat_name, delta_value in stat_changes.items():
                    old_value = npc.stats.get(stat_name, 0)
                    if isinstance(old_value, (int, float)) and isinstance(delta_value, (int, float)):
                        # 숫자면 델타 적용 + 클램프(0~100)
                        new_value = max(0, min(100, old_value + delta_value))
                        npc.stats[stat_name] = new_value
                        debug_entries.append({
                            "type": "npc_stat",
                            "npc_id": npc_id,
                            "stat": stat_name,
                            "old": old_value,
                            "delta": delta_value,
                            "new": new_value
                        })
                    else:
                        # 숫자가 아니면 덮어쓰기
                        npc.stats[stat_name] = delta_value
                        debug_entries.append({
                            "type": "npc_stat_set",
                            "npc_id": npc_id,
                            "stat": stat_name,
                            "value": delta_value
                        })
            else:
                debug_entries.append({
                    "type": "unknown_npc",
                    "npc_id": npc_id,
                    "ignored": True
                })

        # 2. 플래그 적용 (덮어쓰기)
        for key, value in stat_delta.flags.items():
            old_value = state.flags.get(key)
            state.flags[key] = value
            debug_entries.append({
                "type": "flag",
                "key": key,
                "old": old_value,
                "new": value
            })

        # 3. 인벤토리 추가
        for item_id in stat_delta.inventory_add:
            if item_id and item_id not in state.inventory:
                state.inventory.append(item_id)
                debug_entries.append({
                    "type": "inventory_add",
                    "item_id": item_id
                })

        # 4. 인벤토리 제거
        for item_id in stat_delta.inventory_remove:
            if item_id in state.inventory:
                state.inventory.remove(item_id)
                debug_entries.append({
                    "type": "inventory_remove",
                    "item_id": item_id
                })

        # 5. 잠금 상태 적용
        for key, value in stat_delta.locks.items():
            old_value = state.locks.get(key)
            state.locks[key] = value
            debug_entries.append({
                "type": "lock",
                "key": key,
                "old": old_value,
                "new": value
            })

        # 6. 시나리오 변수 적용
        # 스키마에서 범위 정보 가져오기
        var_schema = {}
        if assets:
            var_schema = assets.get_state_schema().get("vars", {})

        for key, value in stat_delta.vars.items():
            old_value = state.vars.get(key, 0)

            if isinstance(old_value, (int, float)) and isinstance(value, (int, float)):
                # 숫자면 델타로 간주하여 더하기
                new_value = old_value + value

                # 스키마에서 min/max 범위 적용
                if key in var_schema:
                    min_val = var_schema[key].get("min", float("-inf"))
                    max_val = var_schema[key].get("max", float("inf"))
                    new_value = max(min_val, min(max_val, new_value))

                state.vars[key] = new_value
            else:
                # bool/str은 덮어쓰기
                state.vars[key] = value
                new_value = value

            debug_entries.append({
                "type": "var",
                "key": key,
                "old": old_value,
                "delta_or_value": value,
                "new": new_value
            })

        # 7. 턴 증가
        if stat_delta.turn_increment > 0:
            old_turn = state.turn
            state.turn += stat_delta.turn_increment
            debug_entries.append({
                "type": "turn",
                "old": old_turn,
                "increment": stat_delta.turn_increment,
                "new": state.turn
            })

        # 8. 메모리 업데이트 적용
        for npc_id, memory_data in stat_delta.memory_updates.items():
            if npc_id in state.npcs:
                npc = state.npcs[npc_id]
                npc.memory.update(memory_data)
                debug_entries.append({
                    "type": "memory_update",
                    "npc_id": npc_id,
                    "data": memory_data
                })

        # 디버그 로그 저장
        self._store.log_debug({
            "user_id": user_id,
            "scenario_id": scenario_id,
            "delta_applied": delta,
            "changes": debug_entries
        })

        logger.info(f"Applied delta: {len(debug_entries)} changes")
        return state

    def persist(
        self,
        user_id: str,
        scenario_id: str,
        world_state: WorldState
    ):
        """
        상태 영속화

        현재는 in-memory 저장이지만, 추후 Redis/DB로 교체 시 이 메서드 수정

        Args:
            user_id: 유저 ID
            scenario_id: 시나리오 ID
            world_state: 저장할 상태
        """
        self._store.set(user_id, scenario_id, world_state)
        logger.debug(f"Persisted state for user={user_id}, scenario={scenario_id}")

    def reset_state(self, user_id: str, scenario_id: str):
        """유저/시나리오의 상태 리셋"""
        self._store.delete(user_id, scenario_id)
        logger.info(f"Reset state for user={user_id}, scenario={scenario_id}")

    def get_debug_log(self) -> list[dict[str, Any]]:
        """디버그 로그 조회"""
        return self._store.get_debug_log()


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴)
# ============================================================
_wsm_instance: Optional[WorldStateManager] = None


def get_world_state_manager() -> WorldStateManager:
    """WorldStateManager 싱글턴 인스턴스 반환"""
    global _wsm_instance
    if _wsm_instance is None:
        _wsm_instance = WorldStateManager()
    return _wsm_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import json
    from pathlib import Path
    from app.loader import ScenarioLoader

    print("=" * 60)
    print("STATE MANAGER 컴포넌트 테스트")
    print("=" * 60)

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 상태 매니저 생성
    wsm = WorldStateManager()
    user_id = "test_user"
    scenario_id = scenarios[0]

    # 초기 상태 생성
    print(f"\n[2] 초기 상태 생성 (user={user_id})")
    state = wsm.get_state(user_id, scenario_id, assets)

    print(f"    - turn: {state.turn}")
    print(f"    - npcs: {list(state.npcs.keys())}")
    print(f"    - inventory: {state.inventory}")
    print(f"    - vars: {state.vars}")
    print(f"    - flags: {state.flags}")

    # NPC 스탯 확인 (Dict 기반)
    for npc_id, npc in state.npcs.items():
        print(f"    - {npc_id} stats: {npc.stats}")

    # 델타 적용 테스트
    print(f"\n[3] 델타 적용 테스트")

    delta1 = {
        "npc_stats": {"family": {"trust": 2, "fear": -1}},
        "vars": {"clue_count": 1, "identity_match_score": 1},
        "turn_increment": 1
    }
    print(f"    델타: {json.dumps(delta1, ensure_ascii=False)}")

    state_after = wsm.apply_delta(user_id, scenario_id, delta1, assets)

    print(f"\n[4] 적용 후 상태:")
    print(f"    - turn: {state_after.turn}")
    if "family" in state_after.npcs:
        print(f"    - family stats: {state_after.npcs['family'].stats}")
    print(f"    - vars: {state_after.vars}")

    # 클램프 테스트
    print(f"\n[5] 클램프 테스트 (0~100 범위)")
    delta2 = {
        "npc_stats": {"family": {"trust": 200}},  # 100 초과
        "vars": {"clue_count": -100}  # 음수
    }
    state_clamped = wsm.apply_delta(user_id, scenario_id, delta2, assets)
    if "family" in state_clamped.npcs:
        print(f"    - trust +200 → {state_clamped.npcs['family'].stats.get('trust')} (max 100)")
    print(f"    - clue_count -100 → {state_clamped.vars.get('clue_count')} (min 0)")

    # 영속화 테스트
    print(f"\n[6] 영속화 테스트")
    wsm.persist(user_id, scenario_id, state_clamped)
    reloaded = wsm.get_state(user_id, scenario_id, assets)
    print(f"    저장 후 다시 로드: turn={reloaded.turn}")

    # 리셋 테스트
    print(f"\n[7] 상태 리셋 테스트")
    wsm.reset_state(user_id, scenario_id)
    fresh_state = wsm.get_state(user_id, scenario_id, assets)
    print(f"    리셋 후: turn={fresh_state.turn}, vars={fresh_state.vars}")

    print("\n" + "=" * 60)
    print("STATE MANAGER 테스트 완료")
    print("=" * 60)
