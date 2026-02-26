"""
test/compare_stepmother_phaseC.py

새엄마 NPC phase C (광기 상태) — 동일 프롬프트 3-way 비교 테스트

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용 프롬프트 출처:
  app/agents/dialogue.py → _build_rich_utterance_prompt()
    - 게임 플레이 중 NPC-플레이어 상호작용 시 실제로 호출되는 메인 프롬프트 빌더
    - [ROLE] / [ABSOLUTE RULES] / [NPC PROFILE] / [현재 상태 가이드] /
      [WORLD SNAPSHOT] / [MEMORY] / [RECENT DIALOGUE] / [YOUR TASK] 구조

  app/agents/dialogue.py → _PHASE_DIRECTIVES["stepmother"][3]
    - phase C 전용 행동 지침 (level=3 = "C단계(극단)")
    - "광기적 집착. 감정이 달콤함↔분노로 폭발적 급변."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
비교 대상:
  ① Qwen base 단독  — LORA_VLLM_BASE_URL에 LORA_BASE_MODEL 직접 요청 (어댑터 없음)
  ② Qwen + LoRA     — UnifiedLLMEngine.generate_vLLM(npc_id="stepmother") 로 stepmother_lora 적용
  ③ LoRA + Post     — ② 결과에 postprocess_npc_dialogue(monstrosity=3) 적용

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
실행:
  python test/compare_stepmother_phaseC.py
  LORA_VLLM_BASE_URL=http://localhost:8001 python test/compare_stepmother_phaseC.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 프로젝트 루트를 path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── 프로젝트 내 재사용 함수 ────────────────────────────────────────────
from app.llm.config import LORA_BASE_MODEL
from app.llm.engine import UnifiedLLMEngine, _strip_chinese_chars
from app.agents.dialogue import _build_rich_utterance_prompt, _PHASE_DIRECTIVES
from app.agents.utils import format_persona, format_emotion
from app.postprocess import postprocess_npc_dialogue


# ── 픽스처: phase C 상황 (탈출 시도 직후, affection 바닥) ───────────────


STEPMOTHER_PERSONA = {
    "values":        "아이는 내 것. 통제가 사랑이다. 저택 밖 세계는 위험하다.",
    "taboos":        "아이가 저택 밖으로 나가도록 허용하거나 독립을 응원하는 말",
    "relationships": "플레이어: 집착적으로 소유하려는 딸/아들",
    "triggers": {
        "plus":  ["엄마에게 순종", "집에 있음", "음식 칭찬", "엄마를 믿겠다는 말"],
        "minus": ["탈출 시도", "외부 언급", "반항", "진짜 엄마 언급"],
    },
}

STEPMOTHER_STATS = {
    "affection": 10,   # 매우 낮음 → 통제적/위협적 반응
    "fear":       9,   # 매우 높음 → 광기 극대화
}

WORLD_SNAPSHOT = {
    "genre":           "심리 공포",
    "tone":            "억압적이고 소름 끼치는",
    "day":             5,
    "turn":            12,
    "suspicion_level": 8,
    "player_humanity": 3,
    "node_id":         "stepmother_room",
    "inventory":       ["가족사진"],
    "flags": {
        "attempted_escape":  True,
        "found_secret_room": True,
    },
}

RECENT_HISTORY   = "플레이어: 나 여기서 나갈 거야."
PLAYER_UTTERANCE = "여기서 나가고 싶어. 진짜 엄마한테 돌아가고 싶어."

MEM_CTX = (
    "- 아이가 5일 전 탈출을 시도했다.\n"
    "- 아이가 비밀 방을 발견했다.\n"
    "- 아이가 가족사진을 들고 다닌다."
)

PLAN_TEXT = "아이가 절대 저택을 떠나지 못하게 막는다. 필요하다면 감금도 불사한다."

# phase_to_level 계산용 (index 2 → level 3)
NPC_PHASES = [
    {"phase_id": "phase_a"},
    {"phase_id": "phase_b"},
    {"phase_id": "phase_c"},
]

PHASE_C_DIRECTIVE = _PHASE_DIRECTIVES["stepmother"][3]


# ── 메인 ──────────────────────────────────────────────────────────────

def main() -> None:
    # ── 서버 URL 확인 ──────────────────────────────────────────────────
    engine = UnifiedLLMEngine()
    lora_url = engine.lora_base_url
    if not lora_url:
        print("[오류] LORA_VLLM_BASE_URL 환경변수가 설정되어 있지 않습니다.")
        print("       .env 파일 또는 환경에 LORA_VLLM_BASE_URL=http://<host>:<port> 를 추가하세요.")
        sys.exit(1)

    # ── 공통 프롬프트 조립 (실제 게임 빌더 그대로) ────────────────────
    persona_str = format_persona(STEPMOTHER_PERSONA)
    emotion_str = format_emotion(STEPMOTHER_STATS)

    prompt = _build_rich_utterance_prompt(
        speaker_id      = "stepmother",
        speaker_name    = "엘리노어",
        speaker_persona = STEPMOTHER_PERSONA,
        persona_str     = persona_str,
        emotion_str     = emotion_str,
        plan_text       = PLAN_TEXT,
        mem_ctx         = MEM_CTX,
        history         = RECENT_HISTORY,
        listener_name   = "플레이어",
        ws              = WORLD_SNAPSHOT,
        phase_level     = 3,
    )

    # ── 헤더 출력 ──────────────────────────────────────────────────────
    sep  = "═" * 62
    dash = "─" * 62

    print()
    print("프롬프트 출처  : app/agents/dialogue.py → _build_rich_utterance_prompt()")
    print("Phase 지침 출처: app/agents/dialogue.py → _PHASE_DIRECTIVES[\"stepmother\"][3]")
    print()
    print("[입력 상황]")
    print(f"  플레이어     : \"{PLAYER_UTTERANCE}\"")
    print(f"  이전 기록    : {RECENT_HISTORY}")
    print(f"  Phase C 지침 : {PHASE_C_DIRECTIVE}")
    print(
        f"  suspicion={WORLD_SNAPSHOT['suspicion_level']}  "
        f"player_humanity={WORLD_SNAPSHOT['player_humanity']}  "
        f"affection={STEPMOTHER_STATS['affection']}  "
        f"fear={STEPMOTHER_STATS['fear']}"
    )
    print()
    print("[ 생성 프롬프트 미리보기 (첫 12줄) ]")
    for line in prompt.splitlines()[:12]:
        print(f"  {line}")
    print("  ...")

    # ── ① Qwen base 단독 ───────────────────────────────────────────────
    print()
    print(sep)
    print(f"① Qwen Base 단독  (model: {LORA_BASE_MODEL})")
    print(f"  서버: {lora_url}  |  어댑터: 없음")
    print(dash)
    lora_text = ""
    try:
        t0 = time.perf_counter()
        resp = engine._client.post(
            f"{lora_url}/v1/completions",
            headers={"Authorization": f"Bearer {engine.api_key}"},
            json={
                "model":       LORA_BASE_MODEL,
                "prompt":      prompt,
                "max_tokens":  150,
                "temperature": 0.7,
                "top_p":       0.9,
            },
        )
        resp.raise_for_status()
        base_elapsed = time.perf_counter() - t0
        base_text = _strip_chinese_chars(resp.json()["choices"][0]["text"].strip())
        print(base_text)
        print(f"\n  ⏱  {base_elapsed:.2f}s")
    except Exception as e:
        print(f"[오류] {e}")

    # ── ② Qwen + LoRA ──────────────────────────────────────────────────
    print()
    print(sep)
    print("② Qwen + LoRA  (adapter: stepmother_lora)")
    print(f"  서버: {lora_url}  |  engine.generate_vLLM(npc_id=\"stepmother\")")
    print(dash)
    try:
        t0 = time.perf_counter()
        lora_text = engine.generate_vLLM(prompt, npc_id="stepmother", max_tokens=150)
        lora_elapsed = time.perf_counter() - t0
        print(lora_text)
        print(f"\n  ⏱  {lora_elapsed:.2f}s")
    except Exception as e:
        print(f"[오류] {e}")
        lora_text = ""

    # ── ③ LoRA + Postprocess ───────────────────────────────────────────
    print()
    print(sep)
    print("③ LoRA + Postprocess  (monstrosity=3 / phase_c)")
    print("  app/postprocess/__init__.py → postprocess_npc_dialogue()")
    print(dash)
    if lora_text:
        post_text = postprocess_npc_dialogue(
            lora_text,
            npc_id     = "stepmother",
            phase_id   = "phase_c",
            npc_phases = NPC_PHASES,
            seed       = 42,
        )
        print(post_text)
    else:
        print("[스킵] ② 출력이 없으므로 후처리 생략")

    print()
    print(sep)


if __name__ == "__main__":
    main()
