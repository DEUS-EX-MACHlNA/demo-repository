"""
레이어별 독립 실행 테스트 스크립트

각 레이어의 입출력을 확인하기 위한 통합 테스트 스크립트입니다.

실행 방법:
    python test_all_layers.py
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_condition_evaluator():
    """ConditionEvaluator 테스트"""
    print("\n" + "=" * 80)
    print("1. CONDITION EVALUATOR 테스트")
    print("=" * 80)

    from app.schemas import NPCState, WorldState
    from app.condition_eval import evaluate_condition

    # 테스트용 월드 상태
    world = WorldState(
        turn=5,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 7, "fear": 3, "suspicion": 4}
            ),
        },
        inventory=["item_button"],
        vars={"humanity": 45, "discovered": True},
        flags={"ending_flag": "stealth"},
    )

    # 테스트 케이스
    test_cases = [
        ("npc.button_mother.trust >= 5", True),
        ("vars.humanity <= 50", True),
        ("vars.discovered == true", True),
        ("flag.ending_flag == 'stealth'", True),
        ("has_item.item_button", True),
        ("turn >= 3", True),
    ]

    passed = 0
    for condition, expected in test_cases:
        result = evaluate_condition(condition, world)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {condition}: {result}")
        if result == expected:
            passed += 1

    print(f"\n결과: {passed}/{len(test_cases)} 통과")
    return passed == len(test_cases)


def test_ending_checker():
    """EndingChecker 테스트"""
    print("\n" + "=" * 80)
    print("2. ENDING CHECKER 테스트")
    print("=" * 80)

    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldState
    from app.ending_checker import get_ending_checker

    # 시나리오 로드
    base_path = Path(__file__).parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("  ⚠ 시나리오가 없습니다!")
        return False

    assets = loader.load(scenarios[0])
    print(f"  시나리오: {assets.scenario.get('title')}")

    checker = get_ending_checker()
    endings = checker.get_all_endings(assets)
    print(f"  정의된 엔딩: {len(endings)}개")

    # 초기 상태 테스트
    world = WorldState(
        turn=1,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 5, "fear": 0, "suspicion": 3}
            ),
        },
        vars={"humanity": 80, "total_suspicion": 3},
    )

    result = checker.check(world, assets)
    print(f"  초기 상태 엔딩 도달: {result.reached}")

    # 조건 충족 테스트
    world2 = WorldState(
        turn=10,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 2, "fear": 8, "suspicion": 9}
            ),
        },
        vars={"humanity": 20, "total_suspicion": 15},
    )

    result2 = checker.check(world2, assets)
    print(f"  조건 충족 시 엔딩 도달: {result2.reached}")
    if result2.reached:
        print(f"    엔딩 ID: {result2.ending.ending_id}")
        print(f"    엔딩명: {result2.ending.name}")

    return True


def test_lock_manager():
    """LockManager 테스트"""
    print("\n" + "=" * 80)
    print("3. LOCK MANAGER 테스트")
    print("=" * 80)

    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldState
    from app.lock_manager import LockManager

    # 시나리오 로드
    base_path = Path(__file__).parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("  ⚠ 시나리오가 없습니다!")
        return False

    assets = loader.load(scenarios[0])
    print(f"  시나리오: {assets.scenario.get('title')}")

    locks_data = assets.extras.get("locks", {})
    locks = locks_data.get("locks", [])
    print(f"  정의된 Lock: {len(locks)}개")

    manager = LockManager()

    # 초기 상태 (lock 미해금)
    world1 = WorldState(
        turn=1,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 3, "fear": 0, "suspicion": 2}
            ),
        },
        vars={"humanity": 80, "total_suspicion": 5},
    )

    result1 = manager.check_unlocks(world1, locks_data)
    print(f"  초기 상태 해금: {len(result1.newly_unlocked)}개")

    # 조건 충족 (suspicion 높음)
    world2 = WorldState(
        turn=5,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 2, "fear": 5, "suspicion": 8}
            ),
        },
        vars={"humanity": 50, "total_suspicion": 17},
    )

    result2 = manager.check_unlocks(world2, locks_data)
    print(f"  조건 충족 시 해금: {len(result2.newly_unlocked)}개")
    for info in result2.newly_unlocked:
        print(f"    - {info.info_id}: {info.info_title}")

    print(f"  전체 해금된 정보: {len(result2.all_unlocked_ids)}개")

    return True


def test_day_controller():
    """DayController 테스트"""
    print("\n" + "=" * 80)
    print("4. DAY CONTROLLER 테스트")
    print("=" * 80)

    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldState
    from app.day_controller import get_day_controller

    # 시나리오 로드
    base_path = Path(__file__).parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("  ⚠ 시나리오가 없습니다!")
        return False

    assets = loader.load(scenarios[0])
    print(f"  시나리오: {assets.scenario.get('title')}")

    # 테스트용 월드 상태
    world = WorldState(
        turn=1,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 3, "fear": 0, "suspicion": 4}
            ),
        },
        inventory=[],
        vars={"humanity": 10, "total_suspicion": 0}
    )

    controller = get_day_controller()

    # 테스트 입력
    test_inputs = [
        "엄마에게 단추가 뭐냐고 물어본다",
        "부엌을 둘러본다",
    ]

    print(f"  테스트 입력: {len(test_inputs)}개")

    for text in test_inputs:
        try:
            result = controller.process(text, world, assets)
            print(f"  ✓ '{text[:20]}...'")
            print(f"    사건: {result.event_description[:1] if result.event_description else 'None'}")
            print(f"    델타 키: {list(result.state_delta.keys())}")
        except Exception as e:
            print(f"  ✗ '{text[:20]}...': {e}")
            return False

    return True


def test_night_controller():
    """NightController 테스트"""
    print("\n" + "=" * 80)
    print("5. NIGHT CONTROLLER 테스트")
    print("=" * 80)

    from app.loader import ScenarioLoader
    from app.schemas import NPCState, WorldState
    from app.night_controller import get_night_controller

    # 시나리오 로드
    base_path = Path(__file__).parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("  ⚠ 시나리오가 없습니다!")
        return False

    assets = loader.load(scenarios[0])
    print(f"  시나리오: {assets.scenario.get('title')}")

    # 테스트용 월드 상태
    world = WorldState(
        turn=3,
        npcs={
            "button_mother": NPCState(
                npc_id="button_mother",
                stats={"trust": 3, "fear": 0, "suspicion": 4}
            ),
            "button_father": NPCState(
                npc_id="button_father",
                stats={"trust": 2, "fear": 0, "suspicion": 5}
            ),
            "button_daughter": NPCState(
                npc_id="button_daughter",
                stats={"trust": 3, "fear": 0, "suspicion": 3}
            ),
        },
        inventory=[],
        vars={"humanity": 10, "total_suspicion": 0},
    )

    controller = get_night_controller()

    try:
        print("  밤 페이즈 실행 중...")
        result = controller.process(world, assets)
        print(f"  ✓ 완료")
        print(f"    그룹 대화: {len(result.night_conversation)}개 발화")
        print(f"    night_delta 키: {list(result.night_delta.keys())}")

        # 대화 샘플 출력
        if result.night_conversation:
            print(f"    대화 샘플:")
            for i, utt in enumerate(result.night_conversation[:2], 1):
                print(f"      {i}. {utt['speaker']}: {utt['text'][:40]}...")

        return True
    except Exception as e:
        print(f"  ✗ 에러: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """전체 테스트 실행"""
    print("=" * 80)
    print("레이어별 독립 실행 테스트")
    print("=" * 80)

    tests = [
        ("ConditionEvaluator", test_condition_evaluator),
        ("EndingChecker", test_ending_checker),
        ("LockManager", test_lock_manager),
        ("DayController", test_day_controller),
        ("NightController", test_night_controller),
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

    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\n전체: {total_passed}/{total_tests} 통과")

    return total_passed == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
