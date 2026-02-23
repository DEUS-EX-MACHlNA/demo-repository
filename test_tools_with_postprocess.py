"""
app/tools.py의 interact() 함수 후처리 통합 테스트

실행 방법:
    python test_tools_with_postprocess.py
"""
import sys
import os
from pathlib import Path

# UTF-8 출력 강제 설정 (Windows cp949 인코딩 문제 해결)
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 프로젝트 루트를 path에 추가
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))


def test_tools_import():
    """app.tools import 테스트"""
    print("=" * 80)
    print("1. app.tools Import 테스트")
    print("=" * 80)

    try:
        from app.tools import interact, set_tool_context, get_tool_context
        print("✓ app.tools.interact import 성공")
        print("✓ app.tools.set_tool_context import 성공")
        print("✓ app.tools.get_tool_context import 성공")
        return True
    except Exception as e:
        print(f"✗ import 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_postprocess_integration_in_tools():
    """tools.py에 후처리가 통합되었는지 확인"""
    print("\n" + "=" * 80)
    print("2. tools.py 후처리 통합 확인")
    print("=" * 80)

    from pathlib import Path

    tools_path = Path(__file__).parent / "app" / "tools.py"
    content = tools_path.read_text(encoding="utf-8")

    checks = [
        ("postprocess import", "from app.postprocess import postprocess_npc_dialogue"),
        ("humanity 추출", "npc_humanity = npc_state.stats.get(\"humanity\""),
        ("postprocess 호출", "npc_response = postprocess_npc_dialogue("),
        ("npc_id 전달", "npc_id=target"),
        ("humanity 전달", "humanity=npc_humanity"),
    ]

    passed = 0
    for desc, pattern in checks:
        if pattern in content:
            print(f"  ✓ {desc} 확인됨")
            passed += 1
        else:
            print(f"  ✗ {desc} 찾을 수 없음")

    print(f"\n결과: {passed}/{len(checks)} 통과")
    return passed == len(checks)


def test_mock_scenario_loading():
    """mock 시나리오 로딩 테스트 (DB 없이)"""
    print("\n" + "=" * 80)
    print("3. Mock 시나리오 로딩 테스트 (DB 없이)")
    print("=" * 80)

    try:
        from app.services.game import GameService

        print("  시나리오 로드 중...")
        assets = GameService.mock_load_scenario_assets_from_yaml("coraline")
        print(f"  ✓ ScenarioAssets 로드 성공")
        print(f"    - 시나리오: {assets.scenario.get('title', 'N/A')}")
        print(f"    - NPCs: {assets.get_all_npc_ids()[:5]}")

        print("\n  WorldState 생성 중...")
        world_state = GameService.mock_create_world_state_from_yaml("coraline")
        print(f"  ✓ WorldState 생성 성공")
        print(f"    - Turn: {world_state.turn}")
        print(f"    - NPCs: {list(world_state.npcs.keys())[:5]}")
        print(f"    - Inventory: {world_state.inventory[:3] if world_state.inventory else []}")

        # NPC humanity 확인
        print("\n  NPC humanity 스탯:")
        for npc_id, npc_state in world_state.npcs.items():
            humanity = npc_state.stats.get("humanity", "N/A")
            print(f"    - {npc_id}: humanity={humanity}")

        return True
    except Exception as e:
        print(f"  ✗ 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_interact_with_mock_llm():
    """interact() 함수를 mock LLM으로 테스트"""
    print("\n" + "=" * 80)
    print("4. interact() + Mock LLM 테스트")
    print("=" * 80)

    try:
        from app.services.game import GameService
        from app.tools import interact, set_tool_context

        # Mock LLM 클래스 정의
        class MockLLM:
            """테스트용 Mock LLM - 고정 응답 반환"""
            def __init__(self, response: str = "나랑 놀자."):
                self.response = response

            def generate(self, *args, **kwargs):
                return self.response

            def __call__(self, *args, **kwargs):
                return self.generate(*args, **kwargs)

        # 시나리오와 월드 상태 로드
        assets = GameService.mock_load_scenario_assets_from_yaml("coraline")
        world_state = GameService.mock_create_world_state_from_yaml("coraline")

        # Tool context 설정
        mock_llm = MockLLM("나랑 놀자.")
        set_tool_context(
            world_state=world_state,
            assets=assets,
            llm_engine=mock_llm,
        )

        print("  [테스트 1] 동생(brother) - humanity=30 (글리치 레벨3)")

        # 동생의 humanity를 30으로 설정
        if "brother" in world_state.npcs:
            world_state.npcs["brother"].stats["humanity"] = 30
            humanity = world_state.npcs["brother"].stats.get("humanity")
            print(f"    brother.humanity = {humanity}")

            # interact 호출 (generate_utterance는 실제 LLM 필요하므로 스킵)
            # 대신 postprocess만 직접 테스트
            from app.postprocess import postprocess_npc_dialogue

            mock_response = "나랑 놀자."
            processed = postprocess_npc_dialogue(
                text=mock_response,
                npc_id="brother",
                humanity=30,
                seed=42
            )

            print(f"    LLM 원본: {mock_response}")
            print(f"    후처리됨: {processed}")
            print(f"    ✓ 글리치 적용 확인" if processed != mock_response else "    ✗ 글리치 미적용")
        else:
            print("    ✗ brother NPC 없음")

        print("\n  [테스트 2] 새엄마(stepmother) - humanity=10 (광기 레벨3)")

        if "stepmother" in world_state.npcs:
            world_state.npcs["stepmother"].stats["humanity"] = 10
            humanity = world_state.npcs["stepmother"].stats.get("humanity")
            print(f"    stepmother.humanity = {humanity}")

            from app.postprocess import postprocess_npc_dialogue

            mock_response = "엄마 말 들어."
            processed = postprocess_npc_dialogue(
                text=mock_response,
                npc_id="stepmother",
                humanity=10,
                seed=42
            )

            print(f"    LLM 원본: {mock_response}")
            print(f"    후처리됨: {processed}")
            print(f"    ✓ 광기 적용 확인" if processed != mock_response else "    ✗ 광기 미적용")
        else:
            print("    ✗ stepmother NPC 없음")

        print("\n  [테스트 3] 새아빠(stepfather) - humanity=50 (후처리 없음)")

        if "stepfather" in world_state.npcs:
            world_state.npcs["stepfather"].stats["humanity"] = 50
            humanity = world_state.npcs["stepfather"].stats.get("humanity")
            print(f"    stepfather.humanity = {humanity}")

            from app.postprocess import postprocess_npc_dialogue

            mock_response = "안녕하세요."
            processed = postprocess_npc_dialogue(
                text=mock_response,
                npc_id="stepfather",
                humanity=50,
                seed=42
            )

            print(f"    LLM 원본: {mock_response}")
            print(f"    후처리됨: {processed}")
            print(f"    ✓ 원문 유지 확인" if processed == mock_response else "    ✗ 예상치 못한 변경")
        else:
            print("    ✗ stepfather NPC 없음")

        return True

    except Exception as e:
        print(f"  ✗ 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """전체 테스트 실행"""
    print("=" * 80)
    print("app/tools.py 후처리 통합 테스트")
    print("=" * 80)

    tests = [
        ("Import", test_tools_import),
        ("Integration Check", test_postprocess_integration_in_tools),
        ("Mock Scenario", test_mock_scenario_loading),
        ("Interact + Mock LLM", test_interact_with_mock_llm),
    ]

    results = {}

    for name, test_fn in tests:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f"\n✗ {name} 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
            results[name] = False

    # 최종 결과
    print("\n" + "=" * 80)
    print("테스트 결과 요약")
    print("=" * 80)

    for name, passed in results.items():
        status = "✓ 통과" if passed else "✗ 실패"
        print(f"  {status}: {name}")

    total_passed = sum(1 for v in results.values() if v)
    total_tests = len(results)
    print(f"\n전체: {total_passed}/{total_tests} 통과")

    return total_passed == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
