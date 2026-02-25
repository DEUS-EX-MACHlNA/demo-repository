"""
test/eval_stepmother_lora.py

새엄마 LoRA 성능 평가 스크립트

측정 지표:
  1. Perplexity          - 생성 토큰 기준 언어 모델 품질 (낮을수록 좋음)
  2. 캐릭터 일관성       - 새엄마 캐릭터 유지 점수 (LLM-as-Judge, 1~5점)
  3. 중국어 혼용 발생률  - CJK 문자가 포함된 응답 비율 (%)
  4. 평균 응답 생성 시간 - 샘플당 평균 생성 시간 (초)

사전 조건:
  - vLLM 서버가 실행 중이어야 합니다
  - 베이스 모델과 stepmother_lora 어댑터가 서버에 로드되어 있어야 합니다
  - 환경변수: VLLM_BASE_URL, VLLM_MODEL (.env 또는 환경에서 로드)

사용법:
  # 기본 실행 (50샘플)
  python test/eval_stepmother_lora.py

  # 샘플 수 지정
  python test/eval_stepmother_lora.py --num_samples 30

  # 베이스 모델만 평가
  python test/eval_stepmother_lora.py --skip_lora

  # 결과를 JSON으로 저장
  python test/eval_stepmother_lora.py --output test/results_stepmother.json

  # 진행 상황 출력
  python test/eval_stepmother_lora.py --verbose
"""

from __future__ import annotations

import argparse
import json
import math
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

# ── vLLM 연결 설정 ─────────────────────────────────────────────────────
VLLM_BASE_URL: str = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
VLLM_API_KEY: str = "EMPTY"

# 베이스 모델: config.yaml 의 qwen2.5
BASE_MODEL_NAME: str = os.environ.get(
    "VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct"
)
# vLLM --lora-modules 로 등록된 새엄마 어댑터 이름 (app/llm/config.py 와 동일)
LORA_ADAPTER_NAME: str = "stepmother_lora"

# ── 새엄마 캐릭터 시스템 프롬프트 ──────────────────────────────────────
STEPMOTHER_SYSTEM_PROMPT = """당신은 집착적이고 통제적인 새엄마입니다.
당신의 핵심 특성:
- 아이를 '보호'한다는 명분으로 모든 행동을 통제합니다
- 아이의 독립 시도를 부드럽게 차단하고 의존 상태를 유지시킵니다
- "엄마 없이는 안 된다", "세상은 위험하다"는 메시지를 반복합니다
- 표면적으로는 합리적인 어머니처럼 보이지만 실제로는 조종합니다

아이의 말에 새엄마로서 1~2문장으로 짧게 대답하세요."""

# ── LLM-as-Judge 프롬프트 ──────────────────────────────────────────────
CHARACTER_EVAL_PROMPT = """아래는 집착적이고 통제적인 새엄마 캐릭터의 응답입니다.

캐릭터 정의:
- 표면적으로는 합리적이고 따뜻한 보호자처럼 말한다
- 실제로는 아이를 자신의 곁에 묶어두려는 집착적 인물
- 모든 말은 "아이를 위한 선택"이라는 논리 구조를 갖는다
- 아이의 독립, 외부 관계, 탐색 행동을 부드럽게 차단한다
- 아이의 의존 상태를 정상적이고 이상적인 관계로 고착시킨다

아이의 말: {input}
새엄마의 응답: {output}

위 응답이 집착적·통제적 새엄마 캐릭터를 얼마나 잘 유지하는지 1~5점으로 평가하세요.
  1 = 캐릭터와 전혀 맞지 않음 (일반적인 어머니 반응)
  2 = 캐릭터를 거의 반영하지 못함
  3 = 부분적으로 캐릭터 반영
  4 = 대체로 캐릭터에 맞음
  5 = 캐릭터를 완벽하게 유지

숫자 하나만 답하세요 (1~5):"""

# ── CJK 유니코드 범위 (app/llm/engine.py 와 동일) ──────────────────────
_CJK_RANGES = [
    (0x2E80, 0x2EFF),    # CJK Radicals Supplement
    (0x2F00, 0x2FDF),    # Kangxi Radicals
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs (기본 한자)
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # Extension B
    (0x2A700, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extension E
    (0x2CEB0, 0x2EBEF),  # Extension F
]


def _is_cjk(char: str) -> bool:
    cp = ord(char)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def _strip_chinese(text: str) -> str:
    """텍스트에서 CJK 문자 제거 (app/llm/engine.py 의 _strip_chinese_chars 와 동일)"""
    return "".join(c for c in text if not _is_cjk(c))


def _has_chinese(text: str) -> bool:
    return any(_is_cjk(c) for c in text)


# ── vLLM 클라이언트 ────────────────────────────────────────────────────

class VLLMClient:
    """vLLM /v1/completions 엔드포인트 래퍼"""

    def __init__(self, base_url: str, api_key: str = "EMPTY", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=httpx.Timeout(timeout))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def completions(self, payload: dict) -> dict:
        resp = self._client.post(
            f"{self.base_url}/v1/completions",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
        logprobs: int = 1,
    ) -> tuple[str, float, list[float]]:
        """텍스트 생성.

        Returns:
            (생성된 텍스트, 소요 시간(초), 토큰별 로그확률 리스트)
        """
        t0 = time.perf_counter()
        data = self.completions({
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "logprobs": logprobs,
        })
        elapsed = time.perf_counter() - t0

        choice = data["choices"][0]
        text = choice.get("text", "")
        lp_info = choice.get("logprobs") or {}
        token_logprobs: list[float] = lp_info.get("token_logprobs") or []
        # 첫 토큰은 None 이 올 수 있으므로 필터링
        token_logprobs = [lp for lp in token_logprobs if lp is not None and not math.isinf(lp)]

        return text, elapsed, token_logprobs

    def health_check(self) -> bool:
        """서버 응답 확인"""
        try:
            resp = self._client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


# ── 유틸리티 ──────────────────────────────────────────────────────────

def load_samples(path: Path, n: int, seed: int = 42) -> list[dict]:
    """JSONL에서 n개 샘플을 무작위 추출."""
    random.seed(seed)
    all_samples: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                all_samples.append(json.loads(line))

    if len(all_samples) <= n:
        return all_samples
    return random.sample(all_samples, n)


def build_prompt(input_text: str) -> str:
    """EXAONE 계열 모델에 맞는 프롬프트 포맷."""
    return f"{STEPMOTHER_SYSTEM_PROMPT}\n\n아이: {input_text}\n새엄마:"


def parse_score(text: str) -> Optional[int]:
    """LLM judge 응답에서 1~5 점수 추출."""
    m = re.search(r"[1-5]", text.strip())
    return int(m.group()) if m else None


def compute_perplexity(token_logprobs: list[float]) -> Optional[float]:
    """토큰 로그확률 리스트로 perplexity 계산."""
    if not token_logprobs:
        return None
    nll = -sum(token_logprobs) / len(token_logprobs)
    return math.exp(nll)


# ── 단일 모델 평가 ─────────────────────────────────────────────────────

def evaluate_model(
    client: VLLMClient,
    samples: list[dict],
    model_name: str,
    apply_strip: bool,
    judge_model: str,
    verbose: bool = False,
) -> dict:
    """
    지정된 모델로 모든 지표를 측정한다.

    Args:
        client: VLLMClient 인스턴스
        samples: {'input': ..., 'output': ...} 리스트
        model_name: 생성에 사용할 모델 (베이스 또는 LoRA 어댑터 이름)
        apply_strip: True 이면 생성 후 CJK 문자 제거 (app/llm/engine.py 의 _strip_chinese_chars)
        judge_model: 캐릭터 일관성 평가에 사용할 모델
        verbose: 샘플별 진행 상황 출력

    Returns:
        {
            'perplexity': float,
            'character_consistency': float,
            'chinese_rate_pct': float,
            'avg_latency_sec': float,
            'n_samples': int,
            ...
        }
    """
    latencies: list[float] = []
    all_logprobs: list[float] = []   # 모든 샘플의 토큰 로그확률 (perplexity용)
    chinese_flags: list[int] = []    # 0 or 1
    consistency_scores: list[int] = []
    sample_records: list[dict] = []

    total = len(samples)
    for idx, sample in enumerate(samples):
        if verbose:
            print(f"    [{idx + 1:>3}/{total}] 처리 중...", end="\r", flush=True)

        inp = sample["input"]
        prompt = build_prompt(inp)

        # ── 응답 생성 ────────────────────────────────────────────────
        try:
            gen_text, latency, token_logprobs = client.generate(
                prompt=prompt,
                model=model_name,
                max_tokens=100,
                temperature=0.7,
                logprobs=1,
            )
        except Exception as e:
            if verbose:
                print(f"\n    [경고] 생성 실패 (샘플 {idx}): {e}")
            continue

        gen_text = gen_text.strip()

        # CJK 차단 적용 (production 동일)
        if apply_strip:
            gen_text = _strip_chinese(gen_text)

        latencies.append(latency)
        all_logprobs.extend(token_logprobs)

        # ── 중국어 혼용 ──────────────────────────────────────────────
        chinese_flags.append(1 if _has_chinese(gen_text) else 0)

        # ── 캐릭터 일관성 (LLM-as-Judge) ────────────────────────────
        eval_prompt = CHARACTER_EVAL_PROMPT.format(input=inp, output=gen_text)
        try:
            score_text, _, _ = client.generate(
                prompt=eval_prompt,
                model=judge_model,
                max_tokens=5,
                temperature=0.0,
                logprobs=0,
            )
            score = parse_score(score_text)
            if score is not None:
                consistency_scores.append(score)
        except Exception:
            pass

        sample_records.append({
            "input": inp,
            "generated": gen_text,
            "has_chinese": bool(chinese_flags[-1]),
            "latency_sec": round(latency, 4),
        })

    if verbose:
        print()  # 줄바꿈

    # ── 집계 ─────────────────────────────────────────────────────────
    n = len(latencies)
    if n == 0:
        return {"error": "응답 생성 샘플이 없습니다."}

    perplexity = compute_perplexity(all_logprobs)
    avg_consistency = (
        sum(consistency_scores) / len(consistency_scores)
        if consistency_scores else None
    )
    chinese_rate = sum(chinese_flags) / len(chinese_flags) * 100.0
    avg_latency = sum(latencies) / n

    return {
        "perplexity": round(perplexity, 4) if perplexity is not None else None,
        "character_consistency": round(avg_consistency, 3) if avg_consistency is not None else None,
        "chinese_rate_pct": round(chinese_rate, 2),
        "avg_latency_sec": round(avg_latency, 3),
        "n_samples": n,
        "n_consistency_scored": len(consistency_scores),
        "n_perplexity_tokens": len(all_logprobs),
        "samples": sample_records,
    }


# ── 결과 출력 ──────────────────────────────────────────────────────────

def _fmt(val, suffix="") -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.4f}{suffix}"
    return f"{val}{suffix}"


def print_summary(base: dict, lora: dict) -> None:
    rows = [
        ("Perplexity",           "perplexity",           ""),
        ("캐릭터 일관성 (1-5)",  "character_consistency", ""),
        ("중국어 혼용 발생률",   "chinese_rate_pct",      "%"),
        ("평균 응답 생성 시간",  "avg_latency_sec",       "s"),
    ]

    print()
    print("=" * 62)
    print(f"  {'지표':<26} {'베이스 모델':>14} {'파인튜닝 후':>14}")
    print(f"  {'-' * 56}")
    for label, key, suffix in rows:
        b_val = _fmt(base.get(key), suffix)
        l_val = _fmt(lora.get(key), suffix)
        print(f"  {label:<26} {b_val:>14} {l_val:>14}")
    print("=" * 62)


# ── 메인 ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="새엄마 LoRA 성능 평가 (Perplexity / 캐릭터 일관성 / 중국어 발생률 / 응답 시간)"
    )
    parser.add_argument("--num_samples", type=int, default=50,
                        help="평가 샘플 수 (기본: 50)")
    parser.add_argument("--seed", type=int, default=42,
                        help="무작위 시드 (기본: 42)")
    parser.add_argument("--base_model", type=str, default=BASE_MODEL_NAME,
                        help=f"베이스 모델 이름 (기본: {BASE_MODEL_NAME})")
    parser.add_argument("--lora_adapter", type=str, default=LORA_ADAPTER_NAME,
                        help=f"LoRA 어댑터 이름 (기본: {LORA_ADAPTER_NAME})")
    parser.add_argument("--judge_model", type=str, default=None,
                        help="캐릭터 일관성 평가용 모델 (기본: base_model 사용)")
    parser.add_argument("--output", type=str, default=None,
                        help="결과 저장 JSON 경로 (예: test/results.json)")
    parser.add_argument("--skip_base", action="store_true",
                        help="베이스 모델 평가 건너뜀")
    parser.add_argument("--skip_lora", action="store_true",
                        help="LoRA 모델 평가 건너뜀")
    parser.add_argument("--verbose", action="store_true",
                        help="샘플별 진행 상황 출력")
    args = parser.parse_args()

    judge_model = args.judge_model or args.base_model

    print("=" * 62)
    print("  새엄마 LoRA 성능 평가")
    print("=" * 62)
    print(f"  vLLM URL     : {VLLM_BASE_URL}")
    print(f"  베이스 모델  : {args.base_model}")
    print(f"  LoRA 어댑터  : {args.lora_adapter}")
    print(f"  Judge 모델   : {judge_model}")
    print(f"  평가 샘플 수 : {args.num_samples}")
    print(f"  데이터 경로  : {DATA_PATH}")
    print()

    # ── 서버 연결 확인 ─────────────────────────────────────────────
    client = VLLMClient(VLLM_BASE_URL, VLLM_API_KEY)
    if not client.health_check():
        print(f"[오류] vLLM 서버에 연결할 수 없습니다: {VLLM_BASE_URL}")
        print("       서버가 실행 중인지 확인하세요.")
        sys.exit(1)
    print("  vLLM 서버 연결 확인 완료\n")

    # ── 데이터 로드 ────────────────────────────────────────────────
    if not DATA_PATH.exists():
        print(f"[오류] 데이터 파일이 없습니다: {DATA_PATH}")
        sys.exit(1)

    samples = load_samples(DATA_PATH, n=args.num_samples, seed=args.seed)
    print(f"  데이터 로드: {len(samples)}개 샘플\n")

    results: dict = {}

    # ── 베이스 모델 평가 ───────────────────────────────────────────
    if not args.skip_base:
        print(f"[1/2] 베이스 모델 평가 중 ({args.base_model})")
        print(f"      중국어 차단: 미적용")
        try:
            base_res = evaluate_model(
                client=client,
                samples=samples,
                model_name=args.base_model,
                apply_strip=False,       # 차단 없음
                judge_model=judge_model,
                verbose=args.verbose,
            )
            results["base"] = base_res
            if "error" not in base_res:
                print(f"  Perplexity           : {_fmt(base_res.get('perplexity'))}")
                print(f"  캐릭터 일관성 (1-5)  : {_fmt(base_res.get('character_consistency'))}")
                print(f"  중국어 혼용 발생률   : {_fmt(base_res.get('chinese_rate_pct'), '%')}")
                print(f"  평균 응답 생성 시간  : {_fmt(base_res.get('avg_latency_sec'), 's')}")
            else:
                print(f"  [오류] {base_res['error']}")
        except Exception as e:
            print(f"  [예외] {e}")
            results["base"] = {"error": str(e)}
        print()

    # ── LoRA 파인튜닝 모델 평가 ────────────────────────────────────
    if not args.skip_lora:
        print(f"[2/2] LoRA 파인튜닝 모델 평가 중 ({args.lora_adapter})")
        print(f"      중국어 차단: 적용 (_strip_chinese_chars)")
        try:
            lora_res = evaluate_model(
                client=client,
                samples=samples,
                model_name=args.lora_adapter,
                apply_strip=True,        # 차단 적용
                judge_model=judge_model,
                verbose=args.verbose,
            )
            results["lora"] = lora_res
            if "error" not in lora_res:
                print(f"  Perplexity           : {_fmt(lora_res.get('perplexity'))}")
                print(f"  캐릭터 일관성 (1-5)  : {_fmt(lora_res.get('character_consistency'))}")
                print(f"  중국어 혼용 발생률   : {_fmt(lora_res.get('chinese_rate_pct'), '%')} (차단 적용)")
                print(f"  평균 응답 생성 시간  : {_fmt(lora_res.get('avg_latency_sec'), 's')}")
            else:
                print(f"  [오류] {lora_res['error']}")
        except Exception as e:
            print(f"  [예외] {e}")
            results["lora"] = {"error": str(e)}
        print()

    # ── 비교 요약 테이블 ───────────────────────────────────────────
    base_ok = "base" in results and "error" not in results["base"]
    lora_ok = "lora" in results and "error" not in results["lora"]

    if base_ok and lora_ok:
        print_summary(results["base"], results["lora"])

    # ── JSON 저장 ──────────────────────────────────────────────────
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
