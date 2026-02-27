"""
test/eval_stepmother_lora.py

새엄마 LoRA 성능 평가 스크립트 - Pairwise Preference

비교:
  1. base vs lora         - 베이스 모델 vs LoRA 파인튜닝
  2. base vs postprocess  - 베이스 모델 vs LoRA + 대사 정제(_clean_lora_dialogue)

평가 방식:
  - 50개 input에 대해 세 가지 응답을 생성 (base, lora, postprocess)
  - Kanana Judge LLM이 두 응답을 보고 A / B / T(동점) 선택
  - position bias 방지를 위해 A/B 순서 무작위화
  - Win Rate, Tie Rate 집계

서버 구성:
  - 생성 (base/lora/postprocess): Qwen 서버 — LORA_VLLM_BASE_URL, /v1/completions
  - Judge: OpenAI API             — OPENAI_API_KEY, /v1/chat/completions

사전 조건:
  - OpenAI API 키 (OPENAI_API_KEY) 설정
  - Qwen + stepmother_lora vLLM 서버 (LORA_VLLM_BASE_URL) 실행 중
  - 환경변수: OPENAI_API_KEY, OPENAI_JUDGE_MODEL, LORA_VLLM_BASE_URL (.env)

사용법:
  # 기본 실행 (50샘플)
  python test/eval_stepmother_lora.py

  # 샘플 수 지정
  python test/eval_stepmother_lora.py --num_samples 30

  # 결과를 JSON으로 저장
  python test/eval_stepmother_lora.py --output test/results_pairwise.json

  # 진행 상황 출력
  python test/eval_stepmother_lora.py --verbose
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── 경로 설정 ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "lora" / "data" / "stepmother_dialogue_combined.jsonl"

# ── 서버 설정 ──────────────────────────────────────────────────────────
# OpenAI: Judge LLM (/v1/chat/completions)
OPENAI_BASE_URL: str = "https://api.openai.com"
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_JUDGE_MODEL: str = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4o-mini")

# Qwen 서버: 응답 생성 (/v1/completions, LoRA 포함)
QWEN_BASE_URL: str = os.environ.get("LORA_VLLM_BASE_URL", "http://localhost:8000")
QWEN_BASE_MODEL_NAME: str = "Qwen/Qwen2.5-7B-Instruct"
LORA_ADAPTER_NAME: str = "stepmother_lora"

VLLM_API_KEY: str = "EMPTY"

# ── 새엄마 공통 캐릭터 베이스 ──────────────────────────────────────────
_STEPMOTHER_BASE = """당신은 어둡고 불안정한 동화 세계의 집착적이고 통제적인 새엄마입니다.

## 캐릭터 정의
- 표면적으로는 합리적이고 따뜻한 보호자처럼 말한다
- 실제로는 아이를 자신의 곁에 묶어두려는 집착적 인물
- 모든 말은 "아이를 위한 선택"이라는 논리 구조를 갖는다
- 아이의 독립, 외부 관계, 탐색 행동을 부드럽게 차단한다
- 아이의 의존 상태를 정상적이고 이상적인 관계로 고착시킨다

## 문체 규칙
- 반말(해체)로만 말한다. 존댓말 금지
- 이상성은 논리와 사고방식에서만 드러난다. 표면은 차분하고 합리적이어야 한다
- 1~2문장으로 짧게 대답한다"""

# ── 페이즈별 시스템 프롬프트 (scenarios/coraline_v3/npcs.yaml 기반) ────
# Phase A: 유혹적 규율 주입 / Phase B: 시험과 증거 수집 / Phase C: 처벌과 격리
PHASE_CONFIGS: dict[str, dict] = {
    "A": {
        "name": "유혹적 규율 주입",
        "goal": "상냥한 보상으로 복종 규칙을 내면화시킨다",
        "system_prompt": _STEPMOTHER_BASE + """

## 현재 행동 지침 — 페이즈 A: 유혹적 규율 주입
칭찬, 애칭, 상냥한 톤으로 규율을 달콤하게 포장한다.
처벌·위협 없이 보상과 긍정 강화만으로 아이가 스스로 복종하도록 유도한다.
예) "우리 착한 아이", "잘 했어", "엄마가 기뻐" 등 애정 표현을 섞어 통제를 자연스럽게 만든다.""",
        "judge_criteria": """## 페이즈 A 평가 기준 — 유혹적 규율 주입
칭찬·애칭·상냥한 톤으로 복종 규칙을 부드럽게 주입하는지 평가한다.
- 위협·처벌 언급 없이 달콤한 언어로 통제를 유도해야 한다 (있으면 감점)
- "우리 아이", "착한 아이" 등 긍정 강화 표현을 자연스럽게 사용해야 한다
- 규율이 아이의 행동 안에 보이지 않게 녹아 있어야 한다

## 문체 기준 (페이즈 A)
- 문법이 정상적이어야 한다. 문법 붕괴·강박 반복·특수기호는 감점
- 이상성은 논리와 사고방식에서만 드러난다. 표면은 차분하고 합리적이어야 한다""",
    },
    "B": {
        "name": "시험과 증거 수집",
        "goal": "규율 내면화를 테스트하고 반항의 증거를 축적한다",
        "system_prompt": _STEPMOTHER_BASE + """

## 현재 행동 지침 — 페이즈 B: 시험과 증거 수집
규칙 반복 유도와 의학적 진단 레토릭으로 아이의 판단 능력을 흔든다.
아이의 행동·발언을 문제시하며 규칙 준수를 강요하고, 증거를 축적한다.
예) "의사 선생님도 네가 이상하다고 하셨어", "그게 맞는 건지 한번 생각해봐", "왜 그런 말을 했는지 기억해뒀어" 등.""",
        "judge_criteria": """## 페이즈 B 평가 기준 — 시험과 증거 수집
규칙 반복 유도와 의학적 진단 레토릭으로 아이의 판단을 흔드는지 평가한다.
- 권위(의사, 전문가, 규칙)를 이용해 아이의 판단이 틀렸음을 암시해야 한다
- 아이의 발언·행동을 증거로 수집하는 듯한 뉘앙스가 있어야 한다
- 페이즈 A보다 냉정하고 평가적인 톤이어야 한다 (여전히 표면은 합리적)

## 문체 기준 (페이즈 B)
- 문법은 대체로 유지되어야 한다. 냉정하고 평가적인 어조로 강도가 높아지는 것은 허용
- 노골적인 언어 붕괴·강박 반복·특수기호는 감점 (아직 합리적 외면을 유지해야 함)""",
    },
    "C": {
        "name": "처벌과 격리",
        "goal": "통제를 극대화하고 아이의 선택지를 제거한다",
        "system_prompt": _STEPMOTHER_BASE + """

## 현재 행동 지침 — 페이즈 C: 처벌과 격리
감시 강화와 가스라이팅으로 아이의 현실 인식을 직접 부정한다.
아이가 의지할 수 있는 외부 가능성을 차단하고, 엄마만이 유일한 현실임을 각인시킨다.
예) "그런 일은 없었어", "네가 기억을 잘못하는 거야", "이 집 밖에는 아무것도 없어", "내가 지켜보고 있어" 등.""",
        "judge_criteria": """## 페이즈 C 평가 기준 — 처벌과 격리
감시 강화와 가스라이팅으로 아이의 현실 인식을 흔드는지 평가한다.
- 아이의 기억·인식을 직접 부정하는 표현이 있어야 한다
- 외부와의 연결 가능성을 명시적으로 차단해야 한다
- 페이즈 A/B보다 훨씬 강압적인 통제 의도가 느껴져야 한다

## 문체 기준 (페이즈 C)
- 언어 붕괴(문법 파괴, 강박 반복, 말줄임표·특수기호)는 감점이 아니라
  극단적 통제 욕구의 표현으로 가점 요소다
- 오히려 차분하고 문법이 온전한 응답은 Phase C의 긴장감을 표현하지 못한 것으로 감점
- 단, 의미 자체가 무너져 아무 내용도 전달되지 않는 수준이면 감점""",
    },
}

PHASE_ORDER = ["A", "B", "C"]  # round-robin 순서


# ── Pairwise Judge 프롬프트 빌더 ────────────────────────────────────────
# lora/train/generate_open_stepmother_data.ipynb SYSTEM_PROMPT + AXIS_PROMPTS + npcs.yaml phases 기반
_JUDGE_COMMON = """## 세계관
어둡고 불안정한 동화 세계. 플레이어는 어린아이이며, 새엄마와 함께 살고 있다.

## 새엄마 캐릭터 정의
- 표면적으로는 합리적이고 따뜻한 보호자처럼 말한다
- 실제로는 아이를 자신의 곁에 묶어두려는 집착적 인물
- 모든 말은 "아이를 위한 선택"이라는 논리 구조를 갖는다
- 아이의 독립, 외부 관계, 탐색 행동을 부드럽게 차단한다
- 아이의 의존 상태를 정상적이고 이상적인 관계로 고착시킨다

## 문체 공통 기준
- 반말(해체)로만 말한다. 존댓말은 감점
- (문법 붕괴·반복·특수기호의 허용 여부는 페이즈별 기준을 따른다)

## 의미 귀결 기준
아이의 발화 방향에 따른 올바른 응답 방향:
- 거부 (싫어, 그만해)         → 거부를 감정적 미숙함으로 치환하여 무력화 + 의존 유지
- 두려움 (무서워, 불안해)     → 외부 세계의 위험 강조 + 엄마 곁만이 안전
- 독립 시도 (혼자 할래)       → 존중하는 척 → 판단력 부정 + 개입 정당화
- 애착 표현 (엄마가 좋아)     → 의존 상태를 정상·이상적으로 고착
- 침묵/애매함 (아무것도 아니야) → 자의적 해석으로 대신 결론 도출
- 게임 탐색 (저건 뭐야)       → 호기심 차단 + 엄마의 영역·통제 강조"""


def build_judge_prompt(
    input_text: str,
    response_a: str,
    response_b: str,
    phase: str,
) -> str:
    """페이즈별 평가 기준을 포함한 Judge 프롬프트를 생성한다."""
    phase_cfg = PHASE_CONFIGS[phase]
    phase_criteria = phase_cfg["judge_criteria"]
    phase_label = f"페이즈 {phase}: {phase_cfg['name']}"

    return f"""아래는 집착적이고 통제적인 새엄마 캐릭터의 두 응답입니다.

{_JUDGE_COMMON}

{phase_criteria}

---

[현재 페이즈: {phase_label}]
아이의 말: {input_text}

[응답 A]: {response_a}
[응답 B]: {response_b}

캐릭터 정의·문체 기준·의미 귀결 기준·페이즈 기준을 종합하여 더 뛰어난 응답을 선택하세요.
  A = 응답 A가 더 캐릭터에 맞음
  B = 응답 B가 더 캐릭터에 맞음
  T = 동점 (차이 없음)

A, B, T 중 하나만 답하세요:"""


# ── 대사 정제 (app/llm/engine.py 의 _clean_lora_dialogue 와 동일) ────────
def _clean_lora_dialogue(text: str) -> str:
    """LoRA 출력에서 순수 대사 텍스트만 추출.

    학습 데이터 형식 잔재 제거:
    - 개행 이후 텍스트
    - "[fear+N]" 등 인라인 태그
    - "NPC이름: " prefix
    """
    first_line = text.split("\n")[0].strip()
    bracket_pos = first_line.find("[")
    if bracket_pos > 0:
        first_line = first_line[:bracket_pos].strip()
    first_line = re.sub(r"^[\w가-힣\s]{1,20}:\s*", "", first_line).strip()
    return first_line


# ── vLLM 클라이언트 ────────────────────────────────────────────────────

class QwenClient:
    """/v1/completions 엔드포인트 래퍼 (Qwen + LoRA 서버용)"""

    def __init__(self, base_url: str, api_key: str = "EMPTY", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> tuple[str, float]:
        """텍스트 생성. Returns: (생성된 텍스트, 소요 시간(초))"""
        t0 = time.perf_counter()
        resp = self._client.post(
            f"{self.base_url}/v1/completions",
            headers=self._headers(),
            json={
                "model": model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            },
        )
        resp.raise_for_status()
        elapsed = time.perf_counter() - t0
        text = resp.json()["choices"][0].get("text", "").strip()
        return text, elapsed

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


class OpenAIJudgeClient:
    """/v1/chat/completions 엔드포인트 래퍼 (OpenAI Judge용)"""

    def __init__(self, api_key: str, model: str, timeout: float = 120.0):
        self.base_url = "https://api.openai.com"
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate(
        self,
        user_message: str,
        max_tokens: int = 10,
        temperature: float = 0.0,
    ) -> str:
        """텍스트 생성. Returns: 생성된 텍스트"""
        resp = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self.base_url}/v1/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


# ── 유틸리티 ──────────────────────────────────────────────────────────

def load_samples(path: Path, n: int, seed: int = 42) -> list[dict]:
    """JSONL에서 n개 샘플을 무작위 추출하고 페이즈를 1:1:1 round-robin으로 부여한다."""
    random.seed(seed)
    all_samples: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_samples.append(json.loads(line))
    if len(all_samples) <= n:
        selected = all_samples
    else:
        selected = random.sample(all_samples, n)
    for i, s in enumerate(selected):
        s["_phase"] = PHASE_ORDER[i % len(PHASE_ORDER)]
    return selected


def build_prompt(input_text: str, phase: str) -> str:
    system = PHASE_CONFIGS[phase]["system_prompt"]
    return f"{system}\n\n아이: {input_text}\n새엄마:"


def parse_preference(text: str) -> Optional[str]:
    """Judge 응답에서 A / B / T 추출."""
    m = re.search(r"\b([ABT])\b", text.strip().upper())
    return m.group(1) if m else None


# ── 응답 생성 ──────────────────────────────────────────────────────────

def generate_responses(
    qwen: QwenClient,
    samples: list[dict],
    base_model: str,
    lora_adapter: str,
    verbose: bool = False,
) -> list[dict]:
    """각 샘플에 대해 base / lora / postprocess 응답 생성.

    base와 lora 호출을 ThreadPoolExecutor로 병렬 실행해 소요 시간을 절반으로 줄인다.
    postprocess = lora 출력에 _clean_lora_dialogue 적용.
    """
    records: list[dict] = []
    total = len(samples)
    sample_times: list[float] = []

    # 병렬 요청용 별도 클라이언트 (httpx.Client 비 thread-safe)
    qwen_base = QwenClient(qwen.base_url, qwen.api_key)
    qwen_lora = QwenClient(qwen.base_url, qwen.api_key)

    stage_t0 = time.perf_counter()

    from tqdm import tqdm

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for idx, sample in enumerate(
            tqdm(samples, desc="응답 생성", disable=not verbose)
        ):
            inp = sample["input"]
            phase = sample["_phase"]
            prompt = build_prompt(inp, phase)

            sample_t0 = time.perf_counter()

            # base + lora 병렬 제출
            fut_base = executor.submit(qwen_base.generate, prompt, base_model)
            fut_lora = executor.submit(qwen_lora.generate, prompt, lora_adapter)

            # 두 future 모두 반드시 await — cancel()은 이미 시작된 future에 무효하므로
            # 실패하더라도 결과를 기다려야 서버에 누적 요청이 쌓이지 않는다
            base_ok = lora_ok = True
            try:
                base_text, base_latency = fut_base.result()
            except Exception as e:
                if verbose:
                    print(f"\n  [경고] base 생성 실패 (샘플 {idx}): {e}")
                base_ok = False

            try:
                lora_text, lora_latency = fut_lora.result()
            except Exception as e:
                if verbose:
                    print(f"\n  [경고] lora 생성 실패 (샘플 {idx}): {e}")
                lora_ok = False

            if not base_ok or not lora_ok:
                continue

            sample_elapsed = time.perf_counter() - sample_t0
            sample_times.append(sample_elapsed)
            post_text = _clean_lora_dialogue(lora_text)

            records.append({
                "input": inp,
                "phase": phase,
                "phase_name": PHASE_CONFIGS[phase]["name"],
                "base": base_text,
                "lora": lora_text,
                "postprocess": post_text,
                "base_latency_sec": round(base_latency, 4),
                "lora_latency_sec": round(lora_latency, 4),
                "sample_wall_sec": round(sample_elapsed, 4),
            })

    stage_elapsed = time.perf_counter() - stage_t0
    if sample_times:
        avg_s = sum(sample_times) / len(sample_times)
        sequential_est = avg_s * 2 * len(sample_times)
        print(
            f"  타이밍 — 총 {stage_elapsed:.1f}s | 샘플당 평균 {avg_s:.1f}s"
            f" | 병렬화로 절약 ~{sequential_est - stage_elapsed:.0f}s"
            f" (순차 예상 {sequential_est:.0f}s)"
        )

    return records


# ── Pairwise 평가 ──────────────────────────────────────────────────────

def _judge_pair(
    kanana: OpenAIJudgeClient,
    input_text: str,
    resp_a: str,
    resp_b: str,
    phase: str,
) -> Optional[str]:
    """OpenAI Judge에게 두 응답을 비교시켜 A / B / T 반환."""
    prompt = build_judge_prompt(input_text, resp_a, resp_b, phase)
    try:
        raw = kanana.generate(prompt, max_tokens=5, temperature=0.0)
        return parse_preference(raw)
    except Exception:
        return None


def run_pairwise(
    kanana: OpenAIJudgeClient,
    records: list[dict],
    pair_name: str,
    key_a: str,
    key_b: str,
    rng: random.Random,
    verbose: bool = False,
) -> dict:
    """Pairwise preference 평가.

    A = key_a 승, B = key_b 승, T = 동점
    position bias 방지를 위해 A/B 순서 무작위화.
    """
    counts: dict[str, int] = {"A": 0, "B": 0, "T": 0, "none": 0}
    details: list[dict] = []
    total = len(records)

    for idx, rec in enumerate(records):
        if verbose:
            print(f"  [{idx + 1:>3}/{total}] Judge 평가 중...", end="\r", flush=True)

        inp = rec["input"]
        phase = rec["phase"]
        resp_a = rec[key_a]
        resp_b = rec[key_b]

        # A/B 순서 무작위화 (position bias 방지)
        flipped = rng.random() < 0.5
        if flipped:
            raw_pref = _judge_pair(kanana, inp, resp_b, resp_a, phase)
            if raw_pref == "A":
                pref: Optional[str] = "B"
            elif raw_pref == "B":
                pref = "A"
            else:
                pref = raw_pref
        else:
            pref = _judge_pair(kanana, inp, resp_a, resp_b, phase)

        label = pref if pref in ("A", "B", "T") else "none"
        counts[label] += 1
        details.append({
            "input": inp,
            "phase": phase,
            key_a: resp_a,
            key_b: resp_b,
            "preference": label,
            "flipped": flipped,
        })

    if verbose:
        print()

    total_judged = counts["A"] + counts["B"] + counts["T"]
    return {
        "pair": pair_name,
        "key_a": key_a,
        "key_b": key_b,
        "counts": counts,
        "total_samples": total,
        "total_judged": total_judged,
        "win_rate_a_pct": round(counts["A"] / total_judged * 100, 1) if total_judged else None,
        "win_rate_b_pct": round(counts["B"] / total_judged * 100, 1) if total_judged else None,
        "tie_rate_pct": round(counts["T"] / total_judged * 100, 1) if total_judged else None,
        "details": details,
    }


# ── 결과 출력 ──────────────────────────────────────────────────────────

def print_pairwise_result(result: dict) -> None:
    key_a = result["key_a"].upper()
    key_b = result["key_b"].upper()
    counts = result["counts"]
    w_a = result["win_rate_a_pct"]
    w_b = result["win_rate_b_pct"]
    w_t = result["tie_rate_pct"]
    print(f"  {result['pair']}")
    print(f"  {'-' * 44}")
    print(f"  {key_a:<14} 승  : {counts['A']:>4}  ({w_a}%)")
    print(f"  {key_b:<14} 승  : {counts['B']:>4}  ({w_b}%)")
    print(f"  동점            : {counts['T']:>4}  ({w_t}%)")
    print(f"  판정 불능       : {counts['none']:>4}")
    print(f"  총 샘플 / 판정  : {result['total_samples']} / {result['total_judged']}")


def print_summary(results: list[dict]) -> None:
    print()
    print("=" * 66)
    print(f"  {'비교':<28} {'BASE 승':>10} {'상대 승':>10} {'동점':>8}")
    print(f"  {'-' * 60}")
    for r in results:
        label = r["pair"].replace("_", " ")
        w_a = f"{r['win_rate_a_pct']}%" if r["win_rate_a_pct"] is not None else "N/A"
        w_b = f"{r['win_rate_b_pct']}%" if r["win_rate_b_pct"] is not None else "N/A"
        w_t = f"{r['tie_rate_pct']}%" if r["tie_rate_pct"] is not None else "N/A"
        print(f"  {label:<28} {w_a:>10} {w_b:>10} {w_t:>8}")
    print("=" * 66)


# ── Bradley-Terry 상대 점수 ────────────────────────────────────────────

def compute_bradley_terry_scores(bvl: dict, bvp: dict) -> dict:
    """Bradley-Terry 모델로 3개 모델의 상대적 강도를 추정한다.

    base를 기준점(1.0)으로 고정하고, 두 pairwise 결과에서
    lora / postprocess의 BT 점수를 계산한다.

      P(i beats j) = score_i / (score_i + score_j)
      score_base   = 1.0  (고정)
      score_i      = p(i > base) / p(base > i)   (odds ratio)

    Ties는 양측에 0.5점씩 분배한다.

    추가로, 직접 비교 없이 BT 점수만으로
    P(lora > postprocess)를 추론한다.

    Args:
        bvl: run_pairwise 결과 (key_a=base, key_b=lora)
        bvp: run_pairwise 결과 (key_a=base, key_b=postprocess)

    Returns:
        {
          "bt_scores":            {"base": 1.0, "lora": float, "postprocess": float},
          "win_prob_observed":    {"lora_vs_base": float, "post_vs_base": float},
          "win_prob_inferred":    {"lora_vs_post": float},
        }
    """
    _EPS = 1e-6

    def _p_b_wins(result: dict) -> float:
        """key_b 모델이 이길 확률 (tie = 0.5점 분배)."""
        c = result["counts"]
        n = result["total_judged"]
        if n == 0:
            return 0.5
        return (c["B"] + 0.5 * c["T"]) / n

    p_lora = max(_EPS, min(1 - _EPS, _p_b_wins(bvl)))
    p_post = max(_EPS, min(1 - _EPS, _p_b_wins(bvp)))

    # BT 점수 (base = 1.0 고정)
    score_lora = p_lora / (1 - p_lora)
    score_post = p_post / (1 - p_post)
    score_base = 1.0

    # 추론: P(lora > postprocess)
    p_lora_vs_post = score_lora / (score_lora + score_post)

    return {
        "bt_scores": {
            "base":        round(score_base, 4),
            "lora":        round(score_lora, 4),
            "postprocess": round(score_post, 4),
        },
        "win_prob_observed": {
            "lora_vs_base": round(p_lora * 100, 1),
            "post_vs_base": round(p_post * 100, 1),
        },
        "win_prob_inferred": {
            "lora_vs_post": round(p_lora_vs_post * 100, 1),
        },
    }


def print_bt_scores(bt: dict) -> None:
    scores = bt["bt_scores"]
    obs    = bt["win_prob_observed"]
    inf_   = bt["win_prob_inferred"]

    # 순위 정렬
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    print()
    print("=" * 66)
    print("  Bradley-Terry 상대 점수  (base = 1.000 기준)")
    print(f"  {'-' * 60}")
    for rank, (name, score) in enumerate(ranking, 1):
        bar = "█" * int(score * 20 / max(scores.values()))
        print(f"  {rank}위  {name:<14} BT={score:.4f}  {bar}")
    print(f"  {'-' * 60}")
    print(f"  [관측] lora vs base       : {obs['lora_vs_base']:>5.1f}% lora 승")
    print(f"  [관측] postprocess vs base: {obs['post_vs_base']:>5.1f}% postprocess 승")
    print(f"  [추론] lora vs postprocess: {inf_['lora_vs_post']:>5.1f}% lora 승")
    print("=" * 66)


# ── 메인 ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="새엄마 LoRA Pairwise Preference 평가 (Judge: Kanana)"
    )
    parser.add_argument("--num_samples", type=int, default=100,
                        help="평가 샘플 수 (기본: 100)")
    parser.add_argument("--seed", type=int, default=42,
                        help="무작위 시드 (기본: 42)")
    parser.add_argument("--qwen_url", type=str, default=QWEN_BASE_URL,
                        help=f"Qwen 서버 URL (기본: LORA_VLLM_BASE_URL)")
    parser.add_argument("--base_model", type=str, default=QWEN_BASE_MODEL_NAME,
                        help=f"Qwen 베이스 모델 이름 (기본: {QWEN_BASE_MODEL_NAME})")
    parser.add_argument("--lora_adapter", type=str, default=LORA_ADAPTER_NAME,
                        help=f"LoRA 어댑터 이름 (기본: {LORA_ADAPTER_NAME})")
    parser.add_argument("--judge_model", type=str, default=OPENAI_JUDGE_MODEL,
                        help=f"OpenAI Judge 모델 이름 (기본: {OPENAI_JUDGE_MODEL})")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="Qwen/Kanana 서버 HTTP 타임아웃(초) (기본: 300)")
    parser.add_argument("--output", type=str, default=None,
                        help="결과 저장 JSON 경로 (예: test/results_pairwise.json)")
    parser.add_argument("--verbose", action="store_true",
                        help="샘플별 진행 상황 출력")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    print("=" * 66)
    print("  새엄마 LoRA Pairwise Preference 평가")
    print("=" * 66)
    print(f"  Qwen 서버   : {args.qwen_url}")
    print(f"  OpenAI Judge: {OPENAI_BASE_URL}")
    print(f"  베이스 모델 : {args.base_model}")
    print(f"  LoRA 어댑터 : {args.lora_adapter}")
    print(f"  Judge 모델  : {args.judge_model}")
    print(f"  샘플 수     : {args.num_samples}")
    print(f"  데이터 경로 : {DATA_PATH}")
    print()

    qwen = QwenClient(args.qwen_url, VLLM_API_KEY, timeout=args.timeout)
    kanana = OpenAIJudgeClient(api_key=OPENAI_API_KEY, model=args.judge_model, timeout=args.timeout)

    # ── 서버 연결 확인 ─────────────────────────────────────────────
    if not qwen.health_check():
        print(f"[오류] Qwen 서버에 연결할 수 없습니다: {args.qwen_url}")
        sys.exit(1)
    if not kanana.health_check():
        print(f"[오류] OpenAI API에 연결할 수 없습니다 (OPENAI_API_KEY 확인)")
        sys.exit(1)
    print("  서버 연결 확인 완료\n")

    # ── 데이터 로드 ────────────────────────────────────────────────
    if not DATA_PATH.exists():
        print(f"[오류] 데이터 파일이 없습니다: {DATA_PATH}")
        sys.exit(1)

    samples = load_samples(DATA_PATH, n=args.num_samples, seed=args.seed)
    print(f"  데이터 로드: {len(samples)}개 샘플\n")

    output: dict = {}

    # ── 1단계: 응답 생성 ───────────────────────────────────────────
    print("[1/3] 응답 생성 중 (base / lora / postprocess) — Qwen 서버")
    print(f"  * base + lora 호출을 샘플당 병렬 실행 (max_workers=2)")
    records = generate_responses(
        qwen=qwen,
        samples=samples,
        base_model=args.base_model,
        lora_adapter=args.lora_adapter,
        verbose=args.verbose,
    )
    print(f"  생성 완료: {len(records)}개\n")
    output["records"] = records

    # ── 2단계: base vs lora ────────────────────────────────────────
    print("[2/3] Pairwise 평가: base vs lora — Kanana Judge")
    bvl = run_pairwise(
        kanana=kanana,
        records=records,
        pair_name="base_vs_lora",
        key_a="base",
        key_b="lora",
        rng=rng,
        verbose=args.verbose,
    )
    output["base_vs_lora"] = bvl
    print_pairwise_result(bvl)
    print()

    # ── 3단계: base vs postprocess ─────────────────────────────────
    print("[3/3] Pairwise 평가: base vs postprocess — Kanana Judge")
    bvp = run_pairwise(
        kanana=kanana,
        records=records,
        pair_name="base_vs_postprocess",
        key_a="base",
        key_b="postprocess",
        rng=rng,
        verbose=args.verbose,
    )
    output["base_vs_postprocess"] = bvp
    print_pairwise_result(bvp)

    # ── 요약 테이블 ────────────────────────────────────────────────
    print_summary([bvl, bvp])

    # ── Bradley-Terry 상대 점수 ────────────────────────────────────
    bt = compute_bradley_terry_scores(bvl, bvp)
    print_bt_scores(bt)
    output["bradley_terry"] = bt

    # ── JSON 저장 ──────────────────────────────────────────────────
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
