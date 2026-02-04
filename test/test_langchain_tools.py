"""
test/test_langchain_tools.py
LangChain 기반 tool 함수 디버깅 스크립트

실행 방법:
    # 전체 테스트
    python -m test.test_langchain_tools

    # 개별 테스트
    python -m test.test_langchain_tools --test engine
    python -m test.test_langchain_tools --test tools
    python -m test.test_langchain_tools --test v2

환경변수:
    HF_TOKEN: HuggingFace API 토큰 (필수)
    LANGCHAIN_MODEL: 사용할 모델 (기본: Qwen/Qwen2.5-7B-Instruct)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


def setup_logging(level: int = logging.INFO):
    """로깅 설정"""
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(message)s",
    )


def check_environment():
    """환경변수 확인"""
    print("=" * 60)
    print("환경변수 확인")
    print("=" * 60)

    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        print(f"[O] HF_TOKEN: {hf_token[:10]}...{hf_token[-4:]}")
    else:
        print("[X] HF_TOKEN이 설정되지 않았습니다!")
        print("    export HF_TOKEN=your_huggingface_token")
        return False

    model = os.environ.get("LANGCHAIN_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    print(f"[O] LANGCHAIN_MODEL: {model}")

    return True


def test_langchain_engine():
    """LangChainEngine 테스트"""
    print("\n" + "=" * 60)
    print("1. LangChainEngine 테스트")
    print("=" * 60)

    from app.llm import LangChainEngine

    print("\n[1.1] LangChainEngine 초기화...")
    engine = LangChainEngine()
    print(f"      model: {engine.model}")
    print(f"      base_url: {engine.base_url}")
    print(f"      available: {engine.available}")

    print("\n[1.2] generate() 테스트...")
    prompt = "안녕하세요. 간단히 인사해주세요."
    print(f"      prompt: {prompt}")

    try:
        response = engine.generate(prompt, max_tokens=50)
        print(f"      response: {response[:100]}...")
        print("      [O] generate() 성공")
    except Exception as e:
        print(f"      [X] generate() 실패: {e}")
        return False

    print("\n[1.3] get_llm_with_tools() 테스트...")
    from langchain_core.tools import tool

    @tool
    def dummy_tool(x: str) -> str:
        """더미 툴입니다."""
        return x

    try:
        llm_with_tools = engine.get_llm_with_tools([dummy_tool])
        print(f"      llm_with_tools: {type(llm_with_tools)}")
        print("      [O] get_llm_with_tools() 성공")
    except Exception as e:
        print(f"      [X] get_llm_with_tools() 실패: {e}")
        return False

    return True


def test_tool_functions():
    """@tool 함수 테스트"""
    print("\n" + "=" * 60)
    print("2. Tool 함수 테스트 (tools_langchain.py)")
    print("=" * 60)

    from app.llm import LangChainEngine
    from app.tools_langchain import (
        set_tool_context,
        tool_talk,
        tool_action,
        tool_item,
        AVAILABLE_TOOLS,
    )
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    # 시나리오 로드
    print("\n[2.1] 시나리오 로드...")
    base_path = root / "scenarios"
    loader = ScenarioLoader(base_path)
    scenario_ids = loader.list_scenarios()

    if not scenario_ids:
        print("      [X] 시나리오 없음")
        return False

    scenario_id = scenario_ids[0]
    assets = loader.load(scenario_id)
    print(f"      scenario: {scenario_id}")
    print(f"      NPCs: {assets.get_all_npc_ids()}")
    print(f"      Items: {assets.get_all_item_ids()}")

    # 테스트용 월드 상태
    print("\n[2.2] WorldState 생성...")
    world = WorldState(
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
            "witness": NPCState(npc_id="witness", trust=0, fear=2, suspicion=0),
        },
        inventory=["casefile_brief", "pattern_analyzer"],
        vars={"clue_count": 0, "fabrication_score": 0},
    )
    print(f"      turn: {world.turn}")
    print(f"      npcs: {list(world.npcs.keys())}")
    print(f"      inventory: {world.inventory}")

    # LangChain 엔진
    print("\n[2.3] LangChainEngine 초기화...")
    engine = LangChainEngine()

    # 컨텍스트 설정
    print("\n[2.4] Tool 컨텍스트 설정...")
    set_tool_context(
        world_state=world,
        assets=assets,
        llm_engine=engine,
        memory_llm=None,  # 메모리 LLM 없이 테스트
    )
    print("      [O] 컨텍스트 설정 완료")

    # AVAILABLE_TOOLS 확인
    print(f"\n[2.5] AVAILABLE_TOOLS: {[t.name for t in AVAILABLE_TOOLS]}")

    # tool_talk 테스트
    print("\n[2.6] tool_talk 테스트...")
    npc_id = "family"
    message = "그날 무슨 일이 있었나요?"
    print(f"      npc_id: {npc_id}")
    print(f"      message: {message}")

    try:
        result = tool_talk.invoke({"npc_id": npc_id, "message": message})
        print(f"      event_description: {result.get('event_description', [])[:2]}")
        print(f"      state_delta: {result.get('state_delta', {})}")
        print("      [O] tool_talk 성공")
    except Exception as e:
        print(f"      [X] tool_talk 실패: {e}")

    # tool_action 테스트
    print("\n[2.7] tool_action 테스트...")
    action = "현장 주변을 조사한다"
    print(f"      action: {action}")

    try:
        result = tool_action.invoke({"action_description": action})
        print(f"      event_description: {result.get('event_description', [])[:2]}")
        print(f"      state_delta: {result.get('state_delta', {})}")
        print("      [O] tool_action 성공")
    except Exception as e:
        print(f"      [X] tool_action 실패: {e}")

    # tool_item 테스트
    print("\n[2.8] tool_item 테스트...")
    item_id = "casefile_brief"
    print(f"      item_id: {item_id}")

    try:
        result = tool_item.invoke({"item_id": item_id})
        print(f"      event_description: {result.get('event_description', [])[:2]}")
        print(f"      state_delta: {result.get('state_delta', {})}")
        print("      [O] tool_item 성공")
    except Exception as e:
        print(f"      [X] tool_item 실패: {e}")

    return True


def test_tool_turn_resolution_v2():
    """tool_turn_resolution_v2 통합 테스트"""
    print("\n" + "=" * 60)
    print("3. tool_turn_resolution_v2 통합 테스트")
    print("=" * 60)

    from app.tools import tool_turn_resolution_v2
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState

    # 시나리오 로드
    print("\n[3.1] 시나리오 로드...")
    base_path = root / "scenarios"
    loader = ScenarioLoader(base_path)
    scenario_ids = loader.list_scenarios()

    if not scenario_ids:
        print("      [X] 시나리오 없음")
        return False

    scenario_id = scenario_ids[0]
    assets = loader.load(scenario_id)
    print(f"      scenario: {scenario_id}")

    # 테스트용 월드 상태
    print("\n[3.2] WorldState 생성...")
    world = WorldState(
        turn=1,
        npcs={
            "family": NPCState(npc_id="family", trust=0, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=0, fear=0, suspicion=1),
            "witness": NPCState(npc_id="witness", trust=0, fear=2, suspicion=0),
        },
        inventory=["casefile_brief", "pattern_analyzer"],
        vars={"clue_count": 0, "fabrication_score": 0},
    )

    # 테스트 케이스
    test_cases = [
        ("talk", "목격자에게 '그날 무슨 일이 있었나요?'라고 묻는다"),
        ("action", "현장 주변을 조사한다"),
        ("item", "메모 패드를 사용한다"),
    ]

    for i, (expected_type, user_input) in enumerate(test_cases, 1):
        print(f"\n[3.{i+2}] 테스트 케이스: {expected_type}")
        print(f"      user_input: {user_input}")

        try:
            result = tool_turn_resolution_v2(user_input, world, assets)
            print(f"      event_description: {result.event_description[:2] if result.event_description else []}")
            print(f"      state_delta: {result.state_delta}")
            print(f"      [O] {expected_type} 테스트 성공")
        except Exception as e:
            print(f"      [X] {expected_type} 테스트 실패: {e}")
            import traceback
            traceback.print_exc()

    return True


def main():
    parser = argparse.ArgumentParser(description="LangChain Tools 디버깅")
    parser.add_argument(
        "--test",
        choices=["all", "engine", "tools", "v2"],
        default="all",
        help="실행할 테스트 (기본: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로깅 활성화",
    )
    args = parser.parse_args()

    # 로깅 설정
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    # 환경 확인
    if not check_environment():
        sys.exit(1)

    # 테스트 실행
    tests = {
        "engine": test_langchain_engine,
        "tools": test_tool_functions,
        "v2": test_tool_turn_resolution_v2,
    }

    if args.test == "all":
        for name, test_fn in tests.items():
            try:
                test_fn()
            except Exception as e:
                print(f"\n[X] {name} 테스트 중 예외 발생: {e}")
                import traceback
                traceback.print_exc()
    else:
        test_fn = tests.get(args.test)
        if test_fn:
            try:
                test_fn()
            except Exception as e:
                print(f"\n[X] {args.test} 테스트 중 예외 발생: {e}")
                import traceback
                traceback.print_exc()

    print("\n" + "=" * 60)
    print("디버깅 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
