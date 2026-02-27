"""
app/postprocess 모듈 테스트 스크립트

실행 방법:
    python test_postprocess.py
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


def test_postprocess_modules():
    """후처리 모듈 import 테스트"""
    print("=" * 80)
    print("1. 후처리 모듈 Import 테스트")
    print("=" * 80)

    try:
        from app.postprocess import postprocess_npc_dialogue, humanity_to_level
        print("✓ app.postprocess import 성공")
    except Exception as e:
        print(f"✗ import 실패: {e}")
        return False

    try:
        from app.postprocess.sibling import postprocess as sibling_postprocess
        print("✓ sibling.postprocess import 성공")
    except Exception as e:
        print(f"✗ sibling import 실패: {e}")
        return False

    try:
        from app.postprocess.stepmother import postprocess as stepmother_postprocess
        print("✓ stepmother.postprocess import 성공")
    except Exception as e:
        print(f"✗ stepmother import 실패: {e}")
        return False

    return True


def test_humanity_to_level():
    """humanity → level 변환 테스트"""
    print("\n" + "=" * 80)
    print("2. humanity_to_level 변환 테스트")
    print("=" * 80)

    from app.postprocess import humanity_to_level

    test_cases = [
        (100, 1, "최고 humanity → 정상"),
        (70, 1, "경계값 70 → 정상"),
        (69, 2, "경계값 69 → 혼란"),
        (50, 2, "중간 humanity → 혼란"),
        (40, 2, "경계값 40 → 혼란"),
        (39, 3, "경계값 39 → 인형화/광기"),
        (0, 3, "최저 humanity → 인형화/광기"),
    ]

    passed = 0
    for humanity, expected_level, desc in test_cases:
        result = humanity_to_level(humanity)
        status = "✓" if result == expected_level else "✗"
        print(f"  {status} humanity={humanity:3d} → level={result} (예상: {expected_level}) - {desc}")
        if result == expected_level:
            passed += 1

    print(f"\n결과: {passed}/{len(test_cases)} 통과")
    return passed == len(test_cases)


def test_sibling_postprocess():
    """동생(루카스) 후처리 테스트"""
    print("\n" + "=" * 80)
    print("3. 동생(루카스) 글리치 후처리 테스트")
    print("=" * 80)

    from app.postprocess.sibling import postprocess

    test_cases = [
        ("나랑 놀자.", 1, "레벨1(정상) - 글리치 없음"),
        ("나랑 놀자.", 2, "레벨2(혼란) - 약간의 글리치"),
        ("나랑 놀자.", 3, "레벨3(인형화) - 강한 글리치"),
        ("나 혼자 있기 싫어. 누나 어디 가?", 3, "레벨3 - 복문"),
    ]

    for text, level, desc in test_cases:
        result = postprocess(text, glitch_level=level, seed=42)
        print(f"\n  {desc}")
        print(f"    입력:  {text}")
        print(f"    출력:  {result}")

    return True


def test_stepmother_postprocess():
    """새엄마(엘리노어) 후처리 테스트"""
    print("\n" + "=" * 80)
    print("4. 새엄마(엘리노어) 광기 후처리 테스트")
    print("=" * 80)

    from app.postprocess.stepmother import postprocess

    test_cases = [
        ("엄마 말 들어.", 1, "레벨1(정상) - 광기 없음"),
        ("엄마 말 들어.", 2, "레벨2(중간 광기) - 약간의 광기"),
        ("엄마 말 들어.", 3, "레벨3(완전 광기) - 강한 광기"),
        ("네가 어디 갈 생각을 해봤어? 안 돼.", 3, "레벨3 - 복문"),
    ]

    for text, level, desc in test_cases:
        result = postprocess(text, monstrosity=level, seed=42)
        print(f"\n  {desc}")
        print(f"    입력:  {text}")
        print(f"    출력:  {result}")

    return True


def test_dispatch_function():
    """dispatch 함수 테스트 (npc_id 기반 라우팅)"""
    print("\n" + "=" * 80)
    print("5. postprocess_npc_dialogue Dispatch 테스트")
    print("=" * 80)

    from app.postprocess import postprocess_npc_dialogue

    test_cases = [
        # (text, npc_id, humanity, expected_behavior)
        ("나랑 놀자.", "brother", 30, "동생 글리치 레벨3 적용"),
        ("엄마 말 들어.", "stepmother", 10, "새엄마 광기 레벨3 적용"),
        ("안녕하세요.", "stepfather", 50, "다른 NPC - 후처리 없음"),
        ("안녕하세요.", "dog_baron", 50, "다른 NPC - 후처리 없음"),
    ]

    for text, npc_id, humanity, desc in test_cases:
        result = postprocess_npc_dialogue(text, npc_id, humanity, seed=42)
        changed = "변경됨" if result != text else "원문 유지"
        print(f"\n  {desc}")
        print(f"    npc_id={npc_id}, humanity={humanity}")
        print(f"    입력:  {text}")
        print(f"    출력:  {result} ({changed})")

    return True


def test_quality_gate():
    """품질 검증 게이트 테스트"""
    print("\n" + "=" * 80)
    print("6. Quality Gate 테스트")
    print("=" * 80)

    from app.postprocess.sibling import quality_gate as sibling_qg
    from app.postprocess.stepmother import quality_gate as stepmother_qg

    print("\n  [동생 Quality Gate]")
    test_cases = [
        ("", "빈 출력 → 대체"),
        ("혼자 할 수 있어!", "캐릭터 이탈 → 대체"),
        ("나랑 놀자" * 50, "길이 초과 → 자르기"),
    ]

    for text, desc in test_cases:
        result, issues = sibling_qg(text)
        print(f"    {desc}")
        print(f"      입력:  '{text[:40]}...' (len={len(text)})" if len(text) > 40 else f"      입력:  '{text}'")
        print(f"      출력:  '{result[:40]}...' (len={len(result)})" if len(result) > 40 else f"      출력:  '{result}'")
        print(f"      이슈:  {issues}")

    print("\n  [새엄마 Quality Gate]")
    test_cases = [
        ("", "빈 출력 → 대체"),
        ("네가 할 수 있는 일이 많아.", "캐릭터 이탈 → 대체"),
        ("엄마 말 들어." * 50, "길이 초과 → 자르기"),
    ]

    for text, desc in test_cases:
        result, issues = stepmother_qg(text)
        print(f"    {desc}")
        print(f"      입력:  '{text[:40]}...' (len={len(text)})" if len(text) > 40 else f"      입력:  '{text}'")
        print(f"      출력:  '{result[:40]}...' (len={len(result)})" if len(result) > 40 else f"      출력:  '{result}'")
        print(f"      이슈:  {issues}")

    return True


def main():
    """전체 테스트 실행"""
    print("=" * 80)
    print("app/postprocess 후처리 모듈 테스트")
    print("=" * 80)

    tests = [
        ("Import", test_postprocess_modules),
        ("humanity_to_level", test_humanity_to_level),
        ("Sibling Postprocess", test_sibling_postprocess),
        ("Stepmother Postprocess", test_stepmother_postprocess),
        ("Dispatch Function", test_dispatch_function),
        ("Quality Gate", test_quality_gate),
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
