"""
후처리 간단 테스트 - 의존성 최소화

실행 방법:
    python test_postprocess_simple.py
"""
import sys
from pathlib import Path

# UTF-8 출력 강제 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 프로젝트 루트를 path에 추가
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))


def main():
    """간단 통합 테스트"""
    print("=" * 80)
    print("후처리 통합 간단 테스트")
    print("=" * 80)

    # 1. Import 확인
    print("\n[1] Import 확인")
    from app.postprocess import postprocess_npc_dialogue
    print("  ✓ postprocess_npc_dialogue import 성공")

    # 2. tools.py 통합 확인
    print("\n[2] tools.py 통합 확인")
    tools_path = root / "app" / "tools.py"
    content = tools_path.read_text(encoding="utf-8")

    if "from app.postprocess import postprocess_npc_dialogue" in content:
        print("  ✓ postprocess import 확인")
    else:
        print("  ✗ postprocess import 없음")
        return False

    if "postprocess_npc_dialogue(" in content:
        print("  ✓ postprocess_npc_dialogue() 호출 확인")
    else:
        print("  ✗ postprocess_npc_dialogue() 호출 없음")
        return False

    # 3. 실제 후처리 동작 테스트
    print("\n[3] 후처리 동작 테스트")

    test_cases = [
        ("brother", 30, "나랑 놀자.", "동생 - 글리치 레벨3"),
        ("brother", 70, "나랑 놀자.", "동생 - 글리치 레벨1 (정상)"),
        ("stepmother", 10, "엄마 말 들어.", "새엄마 - 광기 레벨3"),
        ("stepmother", 70, "엄마 말 들어.", "새엄마 - 광기 레벨1 (정상)"),
        ("stepfather", 50, "안녕.", "새아빠 - 후처리 없음"),
    ]

    for npc_id, humanity, text, desc in test_cases:
        result = postprocess_npc_dialogue(text, npc_id, humanity, seed=42)
        changed = "변경됨" if result != text else "원문 유지"
        print(f"\n  {desc}")
        print(f"    npc_id={npc_id}, humanity={humanity}")
        print(f"    입력: {text}")
        print(f"    출력: {result}")
        print(f"    상태: {changed}")

    # 4. humanity → level 변환 확인
    print("\n[4] humanity → level 변환 확인")
    from app.postprocess import humanity_to_level

    test_levels = [
        (100, 1), (70, 1), (69, 2), (50, 2), (40, 2), (39, 3), (0, 3)
    ]

    all_passed = True
    for humanity, expected in test_levels:
        result = humanity_to_level(humanity)
        status = "✓" if result == expected else "✗"
        if result != expected:
            all_passed = False
        print(f"  {status} humanity={humanity:3d} → level={result} (예상: {expected})")

    print("\n" + "=" * 80)
    print("테스트 완료!")
    print("=" * 80)

    if all_passed:
        print("\n✓ 모든 테스트 통과")
        print("\n다음 단계:")
        print("  1. 실제 LLM 서버를 띄우고 게임을 실행해보세요")
        print("  2. brother(동생)과 대화 시 humanity가 낮으면 글리치 효과가 나타납니다")
        print("  3. stepmother(새엄마)와 대화 시 humanity가 낮으면 광기 효과가 나타납니다")
        return True
    else:
        print("\n✗ 일부 테스트 실패")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
