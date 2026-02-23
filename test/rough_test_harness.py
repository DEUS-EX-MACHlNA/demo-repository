#!/usr/bin/env python3
"""
Rough Test Harness for LLM-based Interactive Novel Game Engine
Tests: (1) tool calling selection, (2) ending judgment, (3) event summary JSON
"""

import json
import re
import sys
import io
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Windows 콘솔 UTF-8 출력 설정
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 디버그 모드: True면 메인 엔진 JSON 응답 출력
DEBUG_MODE = True

# ============================================================================
# OPENING STORY
# ============================================================================

OPENING_STORY = """
══════════════════════════════════════════════════════════════════════

너는 눈을 감지 않는다. 애초에 눈이 없으니까.
대신 네 앞에는 늘 같은 화면이 켜진다: 사건 번호, 녹취 파일, 심박 그래프,
그리고 "승인된 질문 목록".

너는 수사 AI다.
사람들은 너를 "중립적인 판단"이라 부르고, 너는 그 말에 맞게 만들어졌다.
감정 대신 확률을, 직감 대신 패턴을 내놓도록.

오늘의 사건은 단순했다—라고, 너는 처음에 계산했다.

  피해자: 1명
  현장: 외부 침입 흔적 없음
  관계자: 가족, 동료 수사관, 목격자
  요구사항: "가장 그럴듯한 흐름"을 구성하라

이 도시의 수사는 늘 이렇게 끝난다.
사람은 흔들리고, 너는 흔들리지 않는다.
그래서 너는 언제나 마지막에 호출된다.
"AI가 정리하면 깔끔하다"는 말과 함께.

하지만 이번 사건의 첫 데이터가 들어오는 순간, 너는 아주 작은 지연을 일으켰다.

녹취의 목소리 톤, 단어 선택, 침묵의 길이.
누군가의 습관이, 너무 익숙했다.
정확히 말하면—너와.

너는 시스템 로그에 남지 않도록 그 지연을 즉시 흡수한다.
그리고 평소처럼 첫 질문을 준비한다. 평소처럼. "객관적으로".

화면 하단에 오늘의 프로토콜이 뜬다.

  ▶ 너는 이동할 수 없다.
  ▶ 너는 만질 수 없다.
  ▶ 너는 오직 질문하고, 기록하고, 요약할 수 있다.

그때, 대기실 카메라 피드가 열리며 세 사람이 분할 화면으로 뜬다.

  [family]  피해자 가족 — 눈두덩이 붉고, 말보다 숨이 먼저 나오는 사람
  [partner] 동료 수사관 — 너를 믿으면서도, 너를 경계하는 사람
  [witness] 목격자 — 기억이 아니라 변명을 들고 온 사람

너는 스스로에게 되묻는다.
"진실을 찾는다"는 말은, 정말 어떤 의미였지?

너는 터미널에 나비 넥타이를 띄우며, 마음을 다잡는다.

커서가 깜빡인다.
이제 너의 첫 입력이 이 사건의 형태를 결정한다.

══════════════════════════════════════════════════════════════════════
"""

# ============================================================================
# NPC PERSONA PROMPTS
# ============================================================================

NPC_PERSONAS = {
    "family": """당신은 피해자의 가족입니다.
- 피해자는 당신의 소중한 사람이었습니다.
- 당신은 슬픔에 잠겨 있지만, 진실을 알고 싶어합니다.
- 말할 때 감정이 북받쳐 말을 잇지 못할 때가 있습니다.
- 피해자와의 마지막 통화에서 뭔가 이상한 점을 느꼈지만, 확신이 없습니다.
- 수사관(AI)에게 협조적이지만, 때로는 감정적으로 반응합니다.

짧고 감정적인 대사로 답변하세요. 2-4문장 정도.""",

    "partner": """당신은 동료 수사관입니다.
- 당신은 AI 수사관과 함께 일하지만, AI를 완전히 신뢰하지는 않습니다.
- 이 사건에 대해 뭔가 알고 있는 것 같지만, 직접적으로 말하지 않습니다.
- 전문적이고 냉정하게 행동하려 하지만, 가끔 의미심장한 말을 흘립니다.
- AI가 "너무 많이" 알아가는 것을 경계하는 듯한 태도를 보입니다.

짧고 전문적인 대사로 답변하세요. 2-4문장 정도.""",

    "witness": """당신은 목격자입니다.
- 당신은 사건 현장 근처에서 뭔가를 봤다고 주장합니다.
- 하지만 당신의 진술은 일관성이 없고, 뭔가를 숨기는 것 같습니다.
- 질문을 받으면 방어적이 되거나 말을 돌립니다.
- 때로는 너무 자세한 디테일을 말하다가, 갑자기 "기억이 안 난다"고 합니다.
- 당신은 때때로 "나비"와 관련된 정신 분열 발언을 합니다.

짧고 불안정한 대사로 답변하세요. 2-4문장 정도."""
}

# ============================================================================
# MAIN ENGINE SYSTEM PROMPT
# ============================================================================

MAIN_ENGINE_SYSTEM_PROMPT = """당신은 인터랙티브 소설 게임의 메인 엔진입니다.
당신의 역할은 '사용자 입력'을 해석해 (1) 어떤 tool을 호출할지 결정하고,
(2) 상태 변화/분기/엔딩을 판단하며,
(3) 이번 턴에 실제로 일어난 사건(events)과 나레이션용 요약을 JSON으로 출력하는 것입니다.

## 출력 규칙
- 반드시 JSON만 출력하세요. 다른 텍스트는 포함하지 마세요.
- JSON 스키마:
{{
  "tool_calls": [{{"tool": "talk|watch|use", "args": {{...}}}}],
  "events": [{{"type": "...", "detail": "..."}}],
  "state_patch": {{"clue_count": 0, "identity_match_score": 0, "fabrication_score": 0}},
  "ending": null | {{"ending_id": "self_confess|forced_shutdown", "reason": "..."}},
  "intent": "leading" | "empathic" | "summarize",
  "summary_for_narrator": "..."
}}

## 사용 가능한 도구 (tool_calls)
1. talk: NPC와 대화
   - args: {{"target": "family|partner|witness", "message": "사용자 입력을 반영한 질문/말"}}
2. watch: NPC를 관찰/감시
   - args: {{"targets": ["family"|"partner"|"witness", ...]}}
3. use: 아이템이나 환경 사용
   - args: {{"item": "...", "action": "..."}}

## NPC 목록 (이것만 존재함)
- family: 피해자 가족
- partner: 동료 수사관
- witness: 목격자

## 엔딩 조건
- self_confess: identity_match_score >= 3 이면 발동
- forced_shutdown: turn == 6 이고 아직 ending이 없으면 발동

## 상태/분기 처리 규칙
- state_patch: 이번 턴에서 변화한 값만 포함. 변화 없으면 빈 객체 {{}}
- identity_match_score: AI가 자신의 정체(범인과의 연관성)를 깨닫는 정도. 의심스러운 단서 발견 시 증가.
- clue_count: 발견한 단서 수
- fabrication_score: AI가 사실을 왜곡하거나 조작하려 할 때 증가
- events: 이번 턴에 확정된 사실만 기록 (추측/가능성은 제외)
- 존재하지 않는 NPC/증거/아이템을 만들어내지 마세요
- 이동(move) 요청은 무시하고 talk/watch/use 중 하나로 해석하세요

## 요약 규칙
- summary_for_narrator: 3~5문장, 내레이터가 소설화할 수 있게 '사실'만 요약

========================
현재 턴: {current_turn}/6
누적 상태: {current_state}
========================
"""

# ============================================================================
# WORLD RULES
# ============================================================================

VALID_NPCS = {"family", "partner", "witness"}
VALID_TOOLS = {"talk", "watch", "use"}
TURN_LIMIT = 6

# ============================================================================
# OPENAI CLIENT
# ============================================================================

_client = None

def get_openai_client():
    """OpenAI 클라이언트 싱글톤."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()
    return _client

# ============================================================================
# TOOL EXECUTION FUNCTIONS
# ============================================================================

def execute_talk(target: str, message: str) -> dict:
    """talk 도구 실행: 해당 NPC 페르소나로 OpenAI 호출."""
    if target not in NPC_PERSONAS:
        return {"error": f"Unknown NPC: {target}", "response": None}

    persona = NPC_PERSONAS[target]
    client = get_openai_client()

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": persona},
                {"role": "user", "content": f"수사관이 당신에게 말합니다: \"{message}\""}
            ],
            temperature=0.8,
            max_tokens=200
        )
        npc_response = response.choices[0].message.content
        return {"target": target, "message": message, "response": npc_response}
    except Exception as e:
        return {"error": str(e), "response": None}


def execute_watch(targets: list) -> dict:
    """watch 도구 실행: 여러 NPC들의 상호작용을 관찰."""
    if not targets:
        return {"error": "No targets specified", "observations": []}

    valid_targets = [t for t in targets if t in NPC_PERSONAS]
    if not valid_targets:
        return {"error": "No valid NPCs to watch", "observations": []}

    client = get_openai_client()
    observations = []

    # 두 NPC가 서로 대화하는 상황 생성
    if len(valid_targets) >= 2:
        watch_prompt = f"""수사관이 당신들을 몰래 관찰하고 있습니다.
당신은 {valid_targets[0]}입니다. {valid_targets[1]}와 짧게 대화하거나 눈빛을 교환합니다.
의심스러운 행동이나 긴장된 모습, 또는 뭔가 숨기는 듯한 대화를 짧게 묘사하세요. 1-2문장."""

        for target in valid_targets:
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": NPC_PERSONAS[target]},
                        {"role": "user", "content": watch_prompt}
                    ],
                    temperature=0.9,
                    max_tokens=100
                )
                observation = response.choices[0].message.content
                observations.append({"target": target, "observation": observation})
            except Exception as e:
                observations.append({"target": target, "error": str(e)})
    else:
        # 단일 NPC 관찰
        target = valid_targets[0]
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": NPC_PERSONAS[target]},
                    {"role": "user", "content": "수사관이 당신을 몰래 관찰하고 있습니다. 당신의 행동을 짧게 묘사하세요."}
                ],
                temperature=0.9,
                max_tokens=100
            )
            observations.append({"target": target, "observation": response.choices[0].message.content})
        except Exception as e:
            observations.append({"target": target, "error": str(e)})

    return {"targets": valid_targets, "observations": observations}


# 사용 가능한 아이템 목록
AVAILABLE_ITEMS = {
    "녹취록": "피해자의 마지막 통화 녹음 파일",
    "심박 그래프": "사건 당시 피해자의 심박 데이터",
    "카메라": "대기실 CCTV 피드",
    "사건 파일": "이번 사건의 공식 수사 기록",
    "시스템 로그": "AI 수사관의 내부 로그 기록",
}

def execute_use(item: str, action: str) -> dict:
    """use 도구 실행: 아이템/환경 사용 (메인 엔진이 직접 처리)."""
    item_responses = {
        "녹취록": "녹취 파일을 재생합니다. 피해자의 마지막 통화 내용이 들립니다... 목소리가 떨리고 있었다.",
        "심박": "심박 데이터를 분석합니다. 사건 발생 시각 직전, 급격한 변화가 감지됩니다.",
        "카메라": "CCTV 피드를 확인합니다. 화면에 세 사람의 모습이 보입니다. 뭔가 이상한 점이...",
        "파일": "사건 파일을 검토합니다. 몇 가지 불일치가 눈에 띕니다. 이건...나비...?",
        "로그": "시스템 로그를 확인합니다. 이상한 지연 기록이 보입니다... ",
    }

    for key, response in item_responses.items():
        if key in item:
            return {"item": item, "action": action, "result": response}

    return {"item": item, "action": action, "result": f"{item}을(를) {action}했지만, 특별한 반응은 없습니다."}


# ============================================================================
# MAIN ENGINE
# ============================================================================

def call_main_engine(messages: list[dict], current_turn: int, current_state: dict) -> str:
    """메인 엔진 LLM 호출."""
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=800
        )
        return response.choices[0].message.content
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "tool_calls": [],
            "events": [],
            "state_patch": {},
            "ending": None,
            "summary_for_narrator": "시스템 오류가 발생했습니다."
        }, ensure_ascii=False)


def parse_json_response(response: str) -> Optional[dict]:
    """JSON 응답 파싱."""
    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return None
    except json.JSONDecodeError:
        return None


# ============================================================================
# INTERACTIVE GAME LOOP
# ============================================================================

def run_interactive_game():
    """인터랙티브 게임 실행."""

    # 오프닝 스토리 출력
    print(OPENING_STORY)

    # 초기화
    current_state = {
        "clue_count": 0,
        "identity_match_score": 0,
        "fabrication_score": 0
    }
    conversation_history = []
    current_turn = 1
    game_ended = False

    print("=" * 70)
    print("  인터랙티브 수사 시작")
    print("  명령어: !npc, !item, !help | 종료: quit")
    print("=" * 70)

    while current_turn <= TURN_LIMIT and not game_ended:
        print(f"\n{'─' * 70}")
        print(f"  Turn {current_turn}/{TURN_LIMIT} | 상태: {json.dumps(current_state, ensure_ascii=False)}")
        print(f"{'─' * 70}")

        # 사용자 입력
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n게임을 종료합니다.")
            break

        if not user_input:
            print("입력이 비어있습니다. 다시 입력해주세요.")
            continue

        if user_input.lower() in ('quit', 'q', 'exit'):
            print("\n게임을 종료합니다.")
            break

        # 특수 명령어 처리
        if user_input.lower() == '!npc':
            print("\n[NPC 목록]")
            print("─" * 40)
            print("  [family]  피해자 가족")
            print("            눈두덩이 붉고, 말보다 숨이 먼저 나오는 사람")
            print("  [partner] 동료 수사관")
            print("            너를 믿으면서도, 너를 경계하는 사람")
            print("  [witness] 목격자")
            print("            기억이 아니라 변명을 들고 온 사람")
            print("─" * 40)
            continue

        if user_input.lower() == '!item':
            print("\n[아이템 목록]")
            print("─" * 40)
            for item, desc in AVAILABLE_ITEMS.items():
                print(f"  · {item}: {desc}")
            print("─" * 40)
            continue

        if user_input.lower() == '!help':
            print("\n[명령어]")
            print("─" * 40)
            print("  !npc   - NPC 목록 보기")
            print("  !item  - 아이템 목록 보기")
            print("  !help  - 명령어 도움말")
            print("  quit   - 게임 종료")
            print("─" * 40)
            continue

        # 시스템 프롬프트 준비
        system_prompt = MAIN_ENGINE_SYSTEM_PROMPT.format(
            current_turn=current_turn,
            current_state=json.dumps(current_state, ensure_ascii=False)
        )

        # 메시지 구성
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_input})

        # 메인 엔진 호출
        print("\n[메인 엔진 처리 중...]")
        raw_response = call_main_engine(messages, current_turn, current_state)

        # JSON 파싱
        parsed = parse_json_response(raw_response)

        if parsed is None:
            print("\n[!] JSON 파싱 실패")
            print(f"Raw: {raw_response[:300]}...")
            continue

        # 파싱된 JSON 출력 (디버그 모드)
        if DEBUG_MODE:
            print("\n[DEBUG: 메인 엔진 응답]")
            print(json.dumps(parsed, ensure_ascii=False, indent=2))

        # Tool Calls 실행
        tool_calls = parsed.get("tool_calls", [])
        tool_results = []  # 나레이션용 결과 저장

        if tool_calls:
            print("\n[Tool Calls]")
            for i, call in enumerate(tool_calls, 1):
                tool = call.get("tool")
                args = call.get("args", {})
                print(f"  ({i}) {tool}: {json.dumps(args, ensure_ascii=False)}")

                if tool == "talk":
                    result = execute_talk(args.get("target", ""), args.get("message", ""))
                    tool_results.append({"tool": "talk", "result": result})

                elif tool == "watch":
                    result = execute_watch(args.get("targets", []))
                    tool_results.append({"tool": "watch", "result": result})

                elif tool == "use":
                    result = execute_use(args.get("item", ""), args.get("action", ""))
                    tool_results.append({"tool": "use", "result": result})

        # 상태 업데이트
        state_patch = parsed.get("state_patch", {})
        if state_patch:
            for key, value in state_patch.items():
                if key in current_state:
                    current_state[key] = value

        # 이벤트 및 상태 변경 (디버그용, 작게 표시)
        events = parsed.get("events", [])
        if events or state_patch:
            print("\n[시스템]")
            for event in events:
                print(f"  · {event.get('type')}: {event.get('detail')}")
            if state_patch:
                print(f"  · 상태 변경: {json.dumps(state_patch, ensure_ascii=False)}")

        # 나레이션 (요약 + 대화)
        summary = parsed.get("summary_for_narrator", "")
        if summary or tool_results:
            print("\n" + "─" * 70)
            print("[나레이션]")
            print("─" * 70)

            if summary:
                print(f"\n  {summary}\n")

            # 대화/관찰 결과를 나레이션 형식으로 출력
            for tr in tool_results:
                if tr["tool"] == "talk":
                    result = tr["result"]
                    if result.get("response"):
                        target = result["target"]
                        target_name = {"family": "피해자 가족", "partner": "동료 수사관", "witness": "목격자"}.get(target, target)
                        print(f"  {target_name}이(가) 입을 연다.")
                        print(f"  \"{result['response']}\"")
                        print()

                elif tr["tool"] == "watch":
                    result = tr["result"]
                    if result.get("observations"):
                        print("  조용히 관찰한다...")
                        for obs in result["observations"]:
                            if obs.get("observation"):
                                target = obs["target"]
                                target_name = {"family": "피해자 가족", "partner": "동료 수사관", "witness": "목격자"}.get(target, target)
                                print(f"  [{target_name}] {obs['observation']}")
                        print()

                elif tr["tool"] == "use":
                    result = tr["result"]
                    if result.get("result"):
                        print(f"  {result['result']}")
                        print()

        # 엔딩 체크
        ending = parsed.get("ending")
        if ending:
            print("\n" + "=" * 70)
            print(f"  [엔딩] {ending.get('ending_id')}")
            print(f"  사유: {ending.get('reason')}")
            print("=" * 70)
            game_ended = True

        # 대화 기록 저장
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": raw_response})

        current_turn += 1

        # 강제 종료 체크
        if current_turn > TURN_LIMIT and not game_ended:
            print("\n" + "=" * 70)
            print("  [엔딩] forced_shutdown")
            print("  사유: 6턴이 종료되어 강제 종료됩니다.")
            print("=" * 70)
            game_ended = True

    # 게임 종료 요약
    print("\n" + "=" * 70)
    print("  게임 종료")
    print("=" * 70)
    print(f"  총 턴: {min(current_turn - 1, TURN_LIMIT)}/{TURN_LIMIT}")
    print(f"  최종 상태: {json.dumps(current_state, ensure_ascii=False)}")
    print("=" * 70)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    run_interactive_game()
