"""
app/narrative.py
Narrative Layer

최종 사용자 출력 텍스트를 조립합니다.

## 모드
- lm=False: 텍스트 블록 단순 조합 (테스트용)
- lm=True: LM을 사용한 소설 형식 생성 (EXAONE-3.5-7.8B-Instruct)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv

from app.loader import ScenarioAssets

# 환경변수 로드
load_dotenv()

logger = logging.getLogger(__name__)


class NarrativeLayer:
    """
    내러티브 레이어

    역할:
    - 이벤트 설명 텍스트 블록과 밤 대화 텍스트 블록을 조합
    - 최종 사용자에게 보여줄 dialogue 생성
    - 시나리오 톤 반영 (assets 활용)
    """

    def __init__(self, enable_lm: bool = True):
        """
        내러티브 레이어 초기화

        Args:
            enable_lm: LM 기반 생성 활성화 여부 (기본: True)
        """
        self._render_log: list[dict[str, Any]] = []

        # LM 모델 (lazy loading)
        self._enable_lm = enable_lm
        self._lm_model = None
        self._lm_tokenizer = None
        self._lm_loaded = False

    def render(
        self,
        text_fragment: str | list[str],
        night_dialogue: str,
        world_before: WorldState,
        world_after: WorldState,
        assets: ScenarioAssets
    ) -> str:
        """
        최종 dialogue 조립

        Args:
            text_fragment: tool 실행 결과 텍스트 (str 또는 event_description list)
            night_dialogue: night_comes 결과 텍스트
            world_before: 액션 전 월드 상태
            world_after: 액션 후 월드 상태
            assets: 시나리오 에셋
            is_observed: 밤 변화 관찰 여부 (True일 때만 night_description 렌더링)
            lm: LM 기반 생성 사용 여부 (None이면 CUDA 사용 가능 시 자동 활성화)

        Returns:
            str: 최종 사용자 출력 텍스트
        """
        logger.info("Rendering narrative")

        parts = []

        # 1. 메인 텍스트 (tool 결과 - event_description list 지원)
        if text_fragment:
            if isinstance(text_fragment, list):
                event_text = "\n".join(s for s in text_fragment if s)
            else:
                event_text = str(text_fragment)
            if event_text:
                parts.append(event_text)

        # 2. 상태 변화 묘사 (선택적)
        state_change_text = self._describe_state_changes(world_before, world_after, assets)
        if state_change_text:
            parts.append(state_change_text)

        # 3. 밤 내러티브
        if night_dialogue:
            parts.append("")  # 빈 줄로 구분
            parts.append("---")
            parts.append(night_dialogue)

        # 4. 턴 정보 (선택적)
        turn_info = self._get_turn_info(world_after, assets)
        if turn_info:
            parts.append("")
            parts.append(turn_info)

        # LM 기반 생성
        if use_lm:
            dialogue = self._render_with_lm(event_description, night_description, assets, is_observed)
        else:
            # 단순 텍스트 조합 (테스트용)
            dialogue = self._render_simple(event_description, night_description, is_observed)

        # 렌더 로그 기록
        self._render_log.append({
            "event_count": len(event_description),
            "night_count": len(night_description),
            "dialogue_length": len(dialogue),
            "is_observed": is_observed,
            "used_lm": use_lm,
        })

        logger.debug(f"Rendered dialogue: {len(dialogue)} chars")
        return dialogue

    def _render_simple(
        self,
        event_description: list[str],
        night_description: list[str],
        is_observed: bool
    ) -> str:
        """
        단순 텍스트 조합 (테스트용)

        Args:
            event_description: 이벤트 설명 리스트
            night_description: 밤 변화 리스트
            is_observed: 밤 변화 관찰 여부

        Returns:
            str: 조합된 텍스트
        """
        parts = []

        # 1. 이벤트 설명
        if event_description:
            parts.extend(event_description)

        # 2. 밤 내러티브 (관찰된 경우에만)
        if is_observed and night_description:
            parts.append("")  # 빈 줄로 구분
            parts.append("---")
            parts.extend(night_description)

        return "\n".join(parts)

    def _load_lm_model(self):
        """LM 모델 로드 (lazy loading)"""
        if self._lm_loaded:
            return

        if not self._enable_lm:
            logger.info("LM-based generation is disabled")
            self._lm_loaded = True
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_name = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"
            hf_token = os.environ.get("HF_TOKEN")

            # CUDA 사용 가능 여부 확인
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading LM model: {model_name} on {device}")

            self._lm_tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                token=hf_token,
                trust_remote_code=True
            )

            # 메모리 최적화 옵션 추가
            self._lm_model = AutoModelForCausalLM.from_pretrained(
                model_name,
                token=hf_token,
                trust_remote_code=True,
                torch_dtype=torch.float16,  # 메모리 사용량 절반으로 줄임
                low_cpu_mem_usage=True,  # CPU 메모리 사용량 최적화
                device_map="auto" if device == "cuda" else "cpu"  # CUDA 사용 가능하면 자동 배치
            )

            logger.info(f"LM model loaded successfully on {device}")
            self._lm_loaded = True

        except Exception as e:
            import traceback
            logger.warning(f"Failed to load LM model: {e}")
            logger.warning(f"Traceback:\n{traceback.format_exc()}")
            logger.warning("Falling back to simple text composition.")
            self._lm_loaded = True
            self._lm_model = None
            self._lm_tokenizer = None

    def _render_with_lm(
        self,
        event_description: list[str],
        night_description: list[str],
        assets: ScenarioAssets,
        is_observed: bool
    ) -> str:
        """
        LM을 사용한 소설 형식 텍스트 생성

        Args:
            event_description: 이벤트 설명 리스트
            night_description: 밤 변화 리스트
            assets: 시나리오 에셋
            is_observed: 밤 변화 관찰 여부

        Returns:
            str: LM이 생성한 소설 형식 텍스트
        """
        # 모델 로드 (첫 호출 시에만)
        self._load_lm_model()

        # 모델 로드 실패 시 단순 조합으로 폴백
        if self._lm_model is None or self._lm_tokenizer is None:
            logger.warning("LM model not available, falling back to simple composition")
            return self._render_simple(event_description, night_description, is_observed)

        # 시나리오 정보 추출
        scenario_title = assets.scenario.get("title", "")
        scenario_genre = assets.scenario.get("genre", "")

        # 프롬프트 구성
        prompt = self._build_narrative_prompt(
            event_description,
            night_description,
            scenario_title,
            scenario_genre,
            is_observed
        )

        # LM 생성
        try:
            generated_text = self._generate_with_lm(prompt)
            return generated_text
        except Exception as e:
            import traceback
            logger.error(f"LM generation failed: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.warning("Falling back to simple composition")
            return self._render_simple(event_description, night_description, is_observed)

    def _build_narrative_prompt(
        self,
        event_description: list[str],
        night_description: list[str],
        scenario_title: str,
        scenario_genre: str,
        is_observed: bool
    ) -> str:
        """
        내러티브 생성 프롬프트 구성

        Args:
            event_description: 이벤트 설명 리스트
            night_description: 밤 변화 리스트
            scenario_title: 시나리오 제목
            scenario_genre: 시나리오 장르
            is_observed: 밤 변화 관찰 여부

        Returns:
            str: 구성된 프롬프트
        """
        # 이벤트 텍스트 구성
        events_text = "\n".join(f"- {event}" for event in event_description) if event_description else "(없음)"

        # 밤 변화는 관찰된 경우에만 프롬프트에 포함
        if is_observed and night_description:
            night_text = "\n".join(f"- {night}" for night in night_description)
            night_section = f"""
[밤의 변화]
{night_text}
"""
        else:
            night_section = ""

        prompt = f"""당신은 {scenario_genre} 장르의 소설 작가입니다.
다음 이벤트들을 바탕으로 몰입감 있고 분위기 있는 텍스트를 작성하세요.

[시나리오: {scenario_title}]

[이벤트]
{events_text}{night_section}
[지시사항]
- 위 정보를 바탕으로 자연스럽고 분위기 있는 서술을 작성하세요.
- 장르의 특성을 살려 긴장감과 몰입감을 높이세요.
- 간결하면서도 임팩트 있게 작성하세요."""

        if is_observed:
            prompt += "\n- 이벤트와 밤의 변화를 자연스럽게 연결하세요."

        prompt += "\n\n[출력]"

        return prompt

    def _generate_with_lm(self, prompt: str, max_new_tokens: int = 512) -> str:
        """
        LM으로 텍스트 생성

        Args:
            prompt: 입력 프롬프트
            max_new_tokens: 최대 생성 토큰 수

        Returns:
            str: 생성된 텍스트
        """
        import torch

        # 토크나이징
        messages = [{"role": "user", "content": prompt}]
        input_ids = self._lm_tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        )

        # 디바이스로 이동
        device = next(self._lm_model.parameters()).device
        input_ids = input_ids.to(device)

        # 생성
        with torch.no_grad():
            outputs = self._lm_model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                eos_token_id=self._lm_tokenizer.eos_token_id,
                pad_token_id=self._lm_tokenizer.pad_token_id,
            )

        # 디코딩
        generated_ids = outputs[0][input_ids.shape[1]:]
        generated_text = self._lm_tokenizer.decode(generated_ids, skip_special_tokens=True)

        # 후처리
        generated_text = generated_text.strip()

        logger.debug(f"Generated text ({len(generated_text)} chars): {generated_text[:100]}...")
        return generated_text

    def get_debug_info(self) -> dict:
        """디버그 정보 반환"""
        return {
            "narrative": "lm_enabled" if self._enable_lm else "text_block_composer",
            "lm_loaded": self._lm_loaded,
            "lm_available": self._lm_model is not None,
            "recent_renders": self._render_log[-5:] if self._render_log else [],
        }


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴)
# ============================================================
_narrative_instance: Optional[NarrativeLayer] = None


def get_narrative_layer() -> NarrativeLayer:
    """NarrativeLayer 싱글턴 인스턴스 반환"""
    global _narrative_instance
    if _narrative_instance is None:
        _narrative_instance = NarrativeLayer()
    return _narrative_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader

    print("=" * 60)
    print("NARRATIVE 컴포넌트 테스트")
    print("=" * 60)

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("❌ 시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 내러티브 레이어
    narrative = NarrativeLayer()

    # 테스트 1: 이벤트만 있는 경우 (밤 변화 관찰 안 됨)
    print(f"\n[2] 이벤트만 렌더링 (is_observed=False)")
    print("-" * 40)

    world_before = WorldState(
        turn=1,
        npcs={"family": NPCState(npc_id="family", trust=3, fear=0, suspicion=0)},
        vars={"clue_count": 0},
    )
    event_description = ["피해자 가족이 고개를 끄덕인다.", "침묵이 흐른다."]

    dialogue = narrative.render(
        text_fragment=event_description,
        night_dialogue="",
        world_before=world_before,
        world_after=world_before,
        assets=assets,
    )
    print(dialogue)

    # 테스트 2: 이벤트와 밤 변화 모두 렌더링 (is_observed=True)
    print(f"\n[3] 이벤트 + 밤 변화 렌더링 (is_observed=True)")
    print("-" * 40)

    dialogue_observed = narrative.render(
        event_description=event_desc,
        night_description=night_desc,
        assets=assets,
        is_observed=True  # 밤 변화 관찰됨
    )
    print(dialogue_observed)

    # 테스트 3: 여러 이벤트 블록 + 밤 변화 관찰됨
    print(f"\n[4] 여러 이벤트 블록 + 밤 변화")
    print("-" * 40)

    multiple_events = [
        "당신은 증거를 분석한다.",
        "패턴이 보이기 시작한다.",
        "모든 것이 한 곳을 가리킨다."
    ]

    dialogue_multiple = narrative.render(
        event_description=multiple_events,
        night_description=["시간이 흘러간다."],
        assets=assets,
        is_observed=True
    )
    print(dialogue_multiple)

    # 테스트 4: 자동 LM 선택 (CUDA 사용 가능하면 LM, 아니면 단순 조합)
    print(f"\n[5] 자동 LM 선택 테스트 (lm=None, is_observed=True)")
    print("-" * 40)

    dialogue_auto = narrative.render(
        event_description=event_desc,
        night_description=night_desc,
        assets=assets,
        is_observed=True,
        lm=None  # CUDA 사용 가능 여부로 자동 결정
    )
    print(dialogue_auto)

    # 테스트 5: 명시적 LM 사용 (lm=True)
    print(f"\n[6] 명시적 LM 사용 테스트 (lm=True, is_observed=False)")
    print("-" * 40)

    dialogue_lm = narrative.render(
        event_description=event_desc,
        night_description=night_desc,
        assets=assets,
        is_observed=False,  # 밤 변화 관찰 안 됨
        lm=True
    )
    print(dialogue_lm)

    print("\n" + "=" * 60)
    print("✅ NARRATIVE 테스트 완료")
    print("=" * 60)
