"""
app/game_loop.py
GameLoop — 게임 세션 오케스트레이션

낮/밤 사이클을 관리하고, 각 컨트롤러와 나레이션 레이어를 연결합니다.

## 파이프라인
- 낮 (Day): ScenarioController → NarrativeLayer.render()
- 밤 (Night): NightController → NarrativeLayer.render_night()

## 사용법
```python
from app.game_loop import GameLoop

loop = GameLoop(scenario_id="coraline")
loop.start()

# 낮 턴 실행
result = loop.day_turn(user_input="부엌칼을 집어든다")

# 밤 페이즈 실행
night_result = loop.night_phase()
print(night_result.night_description)  # 몬스터 소설화된 나레이션
```
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.loader import ScenarioLoader, ScenarioAssets
from app.schemas import WorldState, NPCState, NightResult
from app.narrative import get_narrative_layer, NarrativeLayer
from app.night_controller import get_night_controller, NightController
from app.day_controller import get_day_controller, DayController

logger = logging.getLogger(__name__)


class GameLoop:
    """
    게임 루프 — 낮/밤 사이클 오케스트레이션

    ScenarioController(낮)와 NightController(밤)를 관리하고,
    모든 나레이션을 NarrativeLayer를 통해 생성합니다.
    """

    def __init__(
        self,
        scenario_id: str,
        scenarios_path: Path | str | None = None,
        world: WorldState | None = None,
    ):
        """
        GameLoop 초기화

        Args:
            scenario_id: 시나리오 ID (예: "coraline")
            scenarios_path: 시나리오 폴더 경로 (기본: ./scenarios)
            world: 초기 월드 상태 (None이면 시나리오 기본값 사용)
        """
        self.scenario_id = scenario_id

        # 시나리오 로드
        if scenarios_path is None:
            scenarios_path = Path(__file__).parent.parent / "scenarios"
        self._loader = ScenarioLoader(Path(scenarios_path))
        self._assets = self._loader.load(scenario_id)

        # 월드 상태 초기화
        self._world = world or self._init_world_from_scenario()

        # 컨트롤러 & 나레이션 레이어
        self._night_controller: NightController = get_night_controller()
        self._narrative_layer: NarrativeLayer = get_narrative_layer()

        # 상태 추적
        self._is_night = False
        self._turn_log: list[dict[str, Any]] = []

        logger.info(f"[GameLoop] initialized: scenario={scenario_id}")

    def _init_world_from_scenario(self) -> WorldState:
        """시나리오에서 초기 월드 상태 생성"""
        schema = self._assets.scenario.get("state_schema", {})
        vars_schema = schema.get("vars", {})
        flags_schema = schema.get("flags", {})

        # 기본 vars 초기화
        initial_vars = {}
        for var_name, var_def in vars_schema.items():
            initial_vars[var_name] = var_def.get("default", 0)

        # 기본 flags 초기화
        for flag_name, flag_def in flags_schema.items():
            initial_vars[flag_name] = flag_def.get("default", None)

        # NPC 초기화
        npcs = {}
        for npc_data in self._assets.get_all_npc_ids():
            npc_def = self._assets.get_npc_by_id(npc_data)
            if npc_def:
                stats = npc_def.get("stats", {})
                npcs[npc_data] = NPCState(
                    npc_id=npc_data,
                    trust=stats.get("trust", 0),
                    fear=stats.get("fear", 0),
                    suspicion=stats.get("suspicion", 0),
                    humanity=stats.get("humanity", 10),
                )

        return WorldState(
            turn=1,
            npcs=npcs,
            inventory=[],
            vars=initial_vars,
        )

    @property
    def world(self) -> WorldState:
        """현재 월드 상태"""
        return self._world

    @property
    def assets(self) -> ScenarioAssets:
        """시나리오 에셋"""
        return self._assets

    @property
    def is_night(self) -> bool:
        """현재 밤인지 여부"""
        return self._is_night

    # =========================================================
    # 낮 턴 (Day Turn)
    # =========================================================
    def day_turn(self, user_input: str, llm: Any = None) -> dict[str, Any]:
        """
        낮 턴 실행

        Args:
            user_input: 사용자 입력
            llm: LLM 엔진 (None이면 기본 사용)

        Returns:
            dict: {
                "event_description": [...],
                "state_delta": {...},
                "narrative": str,
            }
        """
        if self._is_night:
            logger.warning("[GameLoop] day_turn called during night phase")

        # DayController로 입력 처리
        day_controller = get_day_controller()
        result = day_controller.process(user_input, self._world, self._assets)

        # 상태 적용
        self._apply_state_delta(result.state_delta)

        # 나레이션 생성 (TODO: NarrativeLayer.render() 사용)
        narrative = "\n".join(result.event_description)

        # 로그 기록
        self._turn_log.append({
            "type": "day",
            "turn": self._world.turn,
            "input": user_input,
            "result": result,
        })

        return {
            "event_description": result.event_description,
            "state_delta": result.state_delta,
            "narrative": narrative,
        }

    # =========================================================
    # 밤 페이즈 (Night Phase)
    # =========================================================
    def night_phase(self) -> NightResult:
        """
        밤 페이즈 실행

        1. NightController.process() → night_conversation, night_delta 생성
        2. 상태 적용

        Returns:
            NightResult: 밤 결과 (night_conversation 포함)
        """
        self._is_night = True
        logger.info(f"[GameLoop] night_phase start: turn={self._world.turn}")

        # Step 1: NightController 처리 (대화 + 스탯 변화)
        night_result = self._night_controller.process(self._world, self._assets)

        # Step 2: 상태 적용
        self._apply_night_delta(night_result.night_delta)

        # 로그 기록
        self._turn_log.append({
            "type": "night",
            "turn": self._world.turn,
            "result": night_result,
        })

        self._is_night = False
        logger.info(f"[GameLoop] night_phase done: turn={self._world.turn}")

        return night_result

    # =========================================================
    # 상태 적용
    # =========================================================
    def _apply_state_delta(self, delta: dict[str, Any]) -> None:
        """낮 턴 결과 적용"""
        # NPC 스탯
        for npc_id, stats in delta.get("npc_stats", {}).items():
            if npc_id in self._world.npcs:
                npc = self._world.npcs[npc_id]
                for stat, value in stats.items():
                    if hasattr(npc, stat):
                        current = getattr(npc, stat)
                        setattr(npc, stat, current + value)

        # vars
        for key, value in delta.get("vars", {}).items():
            if key in self._world.vars:
                if isinstance(self._world.vars[key], (int, float)) and isinstance(value, (int, float)):
                    self._world.vars[key] += value
                else:
                    self._world.vars[key] = value
            else:
                self._world.vars[key] = value

        # 턴 증가
        if delta.get("turn_increment"):
            self._world.turn += delta["turn_increment"]

    def _apply_night_delta(self, delta: dict[str, Any]) -> None:
        """밤 페이즈 결과 적용"""
        self._apply_state_delta(delta)

    # =========================================================
    # 엔딩 체크
    # =========================================================
    def check_ending(self) -> dict[str, Any] | None:
        """
        엔딩 조건 체크

        Returns:
            dict: {"ending_id": str, "name": str, "epilogue": str} 또는 None
        """
        endings = self._assets.scenario.get("endings", [])

        for ending in endings:
            condition = ending.get("condition", "")
            if self._evaluate_condition(condition):
                return {
                    "ending_id": ending.get("ending_id"),
                    "name": ending.get("name"),
                    "epilogue": ending.get("epilogue_prompt", ""),
                }

        return None

    def _evaluate_condition(self, condition: str) -> bool:
        """조건 문자열 평가 (간단한 구현)"""
        if not condition:
            return False

        # vars와 turn을 컨텍스트로 사용
        context = {
            "vars": self._world.vars,
            "turn": self._world.turn,
            "turn_limit": self._assets.get_turn_limit(),
            "ending": self._world.vars.get("ending"),
        }

        # 단순 조건 평가 (보안 주의: 실제 환경에서는 안전한 파서 사용)
        try:
            # vars.xxx >= N 형태 파싱
            if "vars." in condition:
                condition = condition.replace("vars.", "context['vars'].get('") + "', 0)"
                condition = condition.replace(" >= ", "') >= ")
                condition = condition.replace(" <= ", "') <= ")
                condition = condition.replace(" == ", "') == ")
                condition = condition.replace(" > ", "') > ")
                condition = condition.replace(" < ", "') < ")

            return eval(condition, {"context": context, "__builtins__": {}})
        except Exception as e:
            logger.warning(f"[GameLoop] condition eval failed: {condition}, error: {e}")
            return False

    # =========================================================
    # 디버그
    # =========================================================
    def get_debug_info(self) -> dict[str, Any]:
        """디버그 정보"""
        return {
            "scenario_id": self.scenario_id,
            "turn": self._world.turn,
            "is_night": self._is_night,
            "vars": self._world.vars,
            "npcs": {npc_id: npc.to_dict() for npc_id, npc in self._world.npcs.items()},
            "turn_log_count": len(self._turn_log),
        }


# =========================================================
# 싱글턴 (선택적)
# =========================================================
_game_loop_instance: Optional[GameLoop] = None


def get_game_loop(scenario_id: str = "coraline") -> GameLoop:
    """GameLoop 싱글턴 인스턴스"""
    global _game_loop_instance
    if _game_loop_instance is None or _game_loop_instance.scenario_id != scenario_id:
        _game_loop_instance = GameLoop(scenario_id)
    return _game_loop_instance


# =========================================================
# 독립 실행 테스트
# =========================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")

    print("=" * 60)
    print("GAME LOOP 테스트 (코렐라인)")
    print("=" * 60)

    loop = GameLoop(scenario_id="coraline")
    print(f"\n[초기 상태]")
    print(f"  턴: {loop.world.turn}")
    print(f"  인간성: {loop.world.vars.get('humanity')}")
    print(f"  의심도: {loop.world.vars.get('total_suspicion')}")

    # 밤 페이즈 테스트
    print(f"\n[밤 페이즈 실행]")
    night_result = loop.night_phase()

    print(f"\n[밤 결과]")
    print(f"  발화 수: {len(night_result.night_conversation)}")
    print(f"  night_delta: {night_result.night_delta}")
    print(f"\n[그룹 대화]")
    print("-" * 40)
    for utt in night_result.night_conversation:
        print(f"  {utt['speaker']}: {utt['text']}")
    print("-" * 40)

    # 엔딩 체크
    ending = loop.check_ending()
    if ending:
        print(f"\n[엔딩 도달!] {ending['name']}")
        print(f"  {ending['epilogue']}")

    print("\n" + "=" * 60)
    print("GAME LOOP 테스트 완료")
    print("=" * 60)
