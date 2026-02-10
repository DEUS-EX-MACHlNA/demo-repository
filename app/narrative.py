"""
app/narrative.py
Narrative Layer

최종 사용자 출력 텍스트를 조립합니다.

## 모드
- lm=False: 텍스트 블록 단순 조합 (테스트용)
- lm=True: LM을 사용한 소설 형식 생성 (EXAONE-3.5-7.8B-Instruct)

## 사용처
- ScenarioController (낮): render() 메서드
- NightController (밤): render_night() 메서드
"""
from __future__ import annotations

import logging
import random
from typing import Any, Optional, TYPE_CHECKING

from dotenv import load_dotenv

from app.loader import ScenarioAssets
from app.llm import UnifiedLLMEngine

if TYPE_CHECKING:
    from app.schemas import WorldState

# 환경변수 로드
load_dotenv()

# ============================================================
# 전역 인스턴스 (싱글턴)
# ============================================================
_llm_instance: Optional[UnifiedLLMEngine] = None

def _get_llm() -> UnifiedLLMEngine:
    """LLM 엔진 싱글턴 반환"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = UnifiedLLMEngine()
    return _llm_instance

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
        self._model = None
        self._tokenizer = None
        self._lm_loaded = False
    
    def render_day(
        self,
        event_description: list[str],
        state_delta: dict[str, Any],
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        낮 페이즈 최종 dialogue 조립

        Args:
            event_description: tool 실행 결과 텍스트 리스트
            state_delta: 변화된 상태 델타 (변한 값만 포함)
            world_state: 현재 월드 상태 (턴 정보 등)
            assets: 시나리오 에셋

        Returns:
            str: 최종 사용자 출력 텍스트
        """
        logger.info("Rendering narrative (day phase)")

        # CUDA 사용 가능 여부로 LM 사용 결정
        import torch
        use_lm = self._enable_lm and torch.cuda.is_available()

        if use_lm:
            dialogue = self._render_with_lm_day(event_description, state_delta, world_state, assets)
        else:
            dialogue = self._render_simple_day(event_description, state_delta, world_state, assets)

        # 렌더 로그 기록
        self._render_log.append({
            "phase": "day",
            "event_count": len(event_description),
            "state_delta_keys": list(state_delta.keys()),
            "dialogue_length": len(dialogue),
            "used_lm": use_lm,
        })

        logger.debug(f"Rendered dialogue: {len(dialogue)} chars")
        return dialogue

    def _render_simple_day(
        self,
        event_description: list[str],
        state_delta: dict[str, Any],
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        낮 페이즈 단순 텍스트 조합 (non-CUDA 환경용)

        Args:
            event_description: 이벤트 설명 리스트
            state_delta: 변화된 상태 델타
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 조합된 텍스트
        """
        parts = []

        # 1. 이벤트 설명
        if event_description:
            parts.extend(event_description)

        # 2. 상태 변화 묘사
        state_change_text = self._describe_state_delta(state_delta, assets)
        if state_change_text:
            parts.append("")
            parts.append(state_change_text)

        # 3. 턴 정보
        turn_info = self._get_turn_info(world_state, assets)
        if turn_info:
            parts.append("")
            parts.append(turn_info)

        return "\n".join(parts)

    def _describe_state_delta(
        self,
        state_delta: dict[str, Any],
        assets: ScenarioAssets,
    ) -> str:
        """
        state_delta를 파싱하여 상태 변화 묘사 텍스트 생성

        Args:
            state_delta: 변화된 상태 델타
            assets: 시나리오 에셋

        Returns:
            str: 상태 변화 묘사 텍스트
        """
        if not state_delta:
            return ""

        changes = []

        # NPC 상태 변화 (동적 스탯)
        if "npcs" in state_delta:
            for npc_id, npc_delta in state_delta["npcs"].items():
                npc_info = assets.get_npc_by_id(npc_id)
                npc_name = npc_info.get("name", npc_id) if npc_info else npc_id

                for stat_name, delta in npc_delta.items():
                    if not isinstance(delta, (int, float)) or delta == 0:
                        continue
                    sign = f"+{delta}" if delta > 0 else str(delta)
                    direction = "상승" if delta > 0 else "하락"
                    changes.append(f"{npc_name}의 {stat_name}이(가) {direction}했다. ({sign})")

        # 변수 변화
        if "vars" in state_delta:
            for var_name, delta in state_delta["vars"].items():
                if var_name == "humanity":
                    if delta > 0:
                        changes.append(f"인간성이 회복되었다. (+{delta})")
                    elif delta < 0:
                        changes.append(f"인간성이 감소했다. ({delta})")
                elif var_name == "total_suspicion":
                    if delta > 0:
                        changes.append(f"전체 의심도가 상승했다. (+{delta})")

        # 인벤토리 변화
        if "inventory_add" in state_delta:
            for item in state_delta["inventory_add"]:
                changes.append(f"'{item}'을(를) 획득했다.")

        if "inventory_remove" in state_delta:
            for item in state_delta["inventory_remove"]:
                changes.append(f"'{item}'을(를) 잃었다.")

        return "\n".join(changes)

    def _get_turn_info(
        self,
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        턴 정보 텍스트 생성

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 턴 정보 텍스트
        """
        turn = world_state.turn
        turn_limit = assets.get_turn_limit()
        remaining = turn_limit - turn

        if remaining <= 2:
            return f"[턴 {turn}/{turn_limit}] 시간이 얼마 남지 않았다..."
        elif remaining <= 5:
            return f"[턴 {turn}/{turn_limit}]"
        else:
            return ""

    def _load_lm_model(self):
        """LM 모델 로드 (UnifiedLLMEngine)"""
        if self._lm_loaded:
            return

        if not self._enable_lm:
            logger.info("LM-based generation is disabled")
            self._lm_loaded = True
            return

        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            llm_engine = _get_llm()
            logger.info(f"LM model loaded successfully on {device}")
            self._lm_loaded = True
            self._model = llm_engine._model
            self._tokenizer = llm_engine._tokenizer

        except Exception as e:
            import traceback
            logger.warning(f"Failed to load LM model: {e}")
            logger.warning(f"Traceback:\n{traceback.format_exc()}")
            logger.warning("Falling back to simple text composition.")
            self._lm_loaded = True
            self._model = None
            self._tokenizer = None            


    def _render_with_lm_day(
        self,
        event_description: list[str],
        state_delta: dict[str, Any],
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        낮 페이즈 LM을 사용한 소설 형식 텍스트 생성

        Args:
            event_description: 이벤트 설명 리스트
            state_delta: 변화된 상태 델타
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: LM이 생성한 소설 형식 텍스트
        """
        # 모델 로드 (첫 호출 시에만)
        self._load_lm_model()

        # 모델 로드 실패 시 단순 조합으로 폴백
        if self._model is None or self._tokenizer is None:
            logger.warning("LM model not available, falling back to simple composition")
            return self._render_simple_day(event_description, state_delta, world_state, assets)

        # 시나리오 정보 추출
        scenario_title = assets.scenario.get("title", "")
        scenario_genre = assets.scenario.get("genre", "")
        scenario_tone = assets.scenario.get("tone", "")

        # 프롬프트 구성
        prompt = self._build_day_narrative_prompt(
            event_description,
            state_delta,
            world_state,
            scenario_title,
            scenario_genre,
            scenario_tone,
            assets,
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
            return self._render_simple_day(event_description, state_delta, world_state, assets)

    def _build_day_narrative_prompt(
        self,
        event_description: list[str],
        state_delta: dict[str, Any],
        world_state: "WorldState",
        scenario_title: str,
        scenario_genre: str,
        scenario_tone: str,
        assets: ScenarioAssets,
    ) -> str:
        """
        낮 페이즈 내러티브 생성 프롬프트 구성

        Args:
            event_description: 이벤트 설명 리스트
            state_delta: 변화된 상태 델타
            world_state: 현재 월드 상태
            scenario_title: 시나리오 제목
            scenario_genre: 시나리오 장르
            scenario_tone: 시나리오 톤
            assets: 시나리오 에셋

        Returns:
            str: 구성된 프롬프트
        """
        # 이벤트 텍스트 구성
        events_text = "\n".join(f"- {event}" for event in event_description) if event_description else "(없음)"

        # 상태 변화 텍스트 구성
        state_change_text = self._describe_state_delta(state_delta, assets)
        state_section = f"\n[상태 변화]\n{state_change_text}" if state_change_text else ""

        # 턴 정보
        turn = world_state.turn
        turn_limit = assets.get_turn_limit()

        prompt = f"""당신은 {scenario_genre} 장르의 소설 작가입니다.
다음 이벤트들을 바탕으로 몰입감 있고 분위기 있는 텍스트를 작성하세요.

[시나리오: {scenario_title}]
[톤: {scenario_tone}]
[현재 턴: {turn}/{turn_limit}]

[이벤트]
{events_text}{state_section}

[지시사항]
- 위 정보를 바탕으로 자연스럽고 분위기 있는 서술을 작성하세요.
- 장르의 특성을 살려 긴장감과 몰입감을 높이세요.
- 간결하면서도 임팩트 있게 작성하세요 (3~5문장).
- 상태 변화가 있다면 자연스럽게 녹여내세요.

[출력]"""

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
        input_ids = self._tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        )

        # 디바이스로 이동
        device = next(self._model.parameters()).device
        input_ids = input_ids.to(device)

        # 생성
        with torch.no_grad():
            outputs = self._model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                eos_token_id=self._tokenizer.eos_token_id,
                pad_token_id=self._tokenizer.pad_token_id,
            )

        # 디코딩
        generated_ids = outputs[0][input_ids.shape[1]:]
        generated_text = self._tokenizer.decode(generated_ids, skip_special_tokens=True)

        # 후처리
        generated_text = generated_text.strip()

        logger.debug(f"Generated text ({len(generated_text)} chars): {generated_text[:100]}...")
        return generated_text

    def get_debug_info(self) -> dict:
        """디버그 정보 반환"""
        return {
            "narrative": "lm_enabled" if self._enable_lm else "text_block_composer",
            "lm_loaded": self._lm_loaded,
            "lm_available": self._model is not None,
            "recent_renders": self._render_log[-5:] if self._render_log else [],
        }

    # ============================================================
    # 밤 나레이션 전용 메서드 (GameLoop에서 호출)
    # ============================================================
    def render_night(
        self,
        world_state: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[dict[str, str]],
    ) -> str:
        """
        밤 페이즈 나레이션 생성 (GameLoop에서 호출)

        night_conversation(몬스터들의 대화)을 소설 형식으로 변환합니다.
        대화를 인용하고 서술을 붙여 몬스터 소설을 만듭니다.

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋
            night_conversation: 대화 리스트 [{speaker, text}, ...]

        Returns:
            str: 몬스터 소설화된 밤 나레이션 텍스트
        """
        logger.info("Rendering narrative (night phase)")

        # CUDA 사용 가능 여부로 LM 사용 결정
        import torch
        use_lm = self._enable_lm and torch.cuda.is_available()

        if use_lm:
            dialogue = self._render_with_lm_night(world_state, assets, night_conversation)
        else:
            dialogue = self._render_simple_night(world_state, assets, night_conversation)

        # 렌더 로그 기록
        self._render_log.append({
            "phase": "night",
            "conversation_count": len(night_conversation),
            "dialogue_length": len(dialogue),
            "used_lm": use_lm,
        })

        logger.debug(f"Rendered night dialogue: {len(dialogue)} chars")
        return dialogue

    def _render_simple_night(
        self,
        world_state: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[dict[str, str]],
    ) -> str:
        """
        밤 페이즈 단순 소설화 (non-CUDA 환경용)

        대화를 인용하고 간단한 서술을 붙여 소설 형식으로 변환합니다.

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋
            night_conversation: 대화 리스트 [{speaker, text}, ...]

        Returns:
            str: 소설화된 텍스트
        """
        if not night_conversation:
            return "밤이 고요히 지나간다."

        parts = []
        parts.append("---")
        parts.append("")

        # 도입부
        humanity = world_state.vars.get("humanity", 10)
        total_suspicion = world_state.vars.get("total_suspicion", 0)

        if total_suspicion >= 10:
            parts.append("어둠 속에서 단추 눈들이 번뜩인다. 가족 회의가 시작되었다.")
        elif total_suspicion >= 5:
            parts.append("밤이 깊어지고, 인형 가족이 모여앉는다.")
        else:
            parts.append("조용한 밤. 어딘가에서 속삭임이 들려온다.")

        parts.append("")

        # 대화를 소설 형식으로 변환
        prev_speaker = None
        for utt in night_conversation:
            speaker_id = utt.get("speaker", "")
            text = utt.get("text", "")

            # NPC 이름 가져오기
            npc_info = assets.get_npc_by_id(speaker_id)
            speaker_name = npc_info.get("name", speaker_id) if npc_info else speaker_id

            # 화자 전환 시 서술 추가
            if speaker_id != prev_speaker:
                if prev_speaker is not None:
                    parts.append("")
                parts.append(f"{speaker_name}이(가) 말했다.")

            # 대사 인용
            parts.append(f'"{text}"')
            prev_speaker = speaker_id

        parts.append("")

        # 마무리
        if humanity <= 3:
            parts.append("대화가 끝났다. 그들의 시선이 네 방을 향한다.")
        elif total_suspicion >= 8:
            parts.append("불길한 침묵이 내려앉는다.")
        else:
            parts.append("대화가 끝나고, 다시 정적이 찾아온다.")

        return "\n".join(parts)

    def _render_with_lm_night(
        self,
        world_state: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[dict[str, str]],
    ) -> str:
        """
        밤 페이즈 LM을 사용한 소설 형식 텍스트 생성

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋
            night_conversation: 대화 리스트 [{speaker, text}, ...]

        Returns:
            str: LM이 생성한 소설 형식 텍스트
        """
        # 모델 로드 (첫 호출 시에만)
        self._load_lm_model()

        # 모델 로드 실패 시 단순 조합으로 폴백
        if self._model is None or self._tokenizer is None:
            logger.warning("LM model not available, falling back to simple composition")
            return self._render_simple_night(world_state, assets, night_conversation)

        # 프롬프트 구성
        prompt = self._build_night_narrative_prompt(world_state, assets, night_conversation)

        # LM 생성
        try:
            generated_text = self._generate_with_lm(prompt, max_new_tokens=400)
            return "---\n\n" + generated_text
        except Exception as e:
            import traceback
            logger.error(f"LM generation failed: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.warning("Falling back to simple composition")
            return self._render_simple_night(world_state, assets, night_conversation)

    def _build_night_narrative_prompt(
        self,
        world_state: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[dict[str, str]],
    ) -> str:
        """
        밤 페이즈 내러티브 생성 프롬프트 구성

        Args:
            world_state: 현재 월드 상태
            assets: 시나리오 에셋
            night_conversation: 대화 리스트

        Returns:
            str: 구성된 프롬프트
        """
        # 시나리오 정보
        scenario_title = assets.scenario.get("title", "")
        scenario_tone = assets.scenario.get("tone", "")

        # 상태 정보
        turn = world_state.turn
        turn_limit = assets.get_turn_limit()
        humanity = world_state.vars.get("humanity", 10)
        total_suspicion = world_state.vars.get("total_suspicion", 0)

        # 대화 텍스트 구성
        conversation_lines = []
        for utt in night_conversation:
            speaker_id = utt.get("speaker", "")
            text = utt.get("text", "")
            npc_info = assets.get_npc_by_id(speaker_id)
            speaker_name = npc_info.get("name", speaker_id) if npc_info else speaker_id
            conversation_lines.append(f"{speaker_name}: \"{text}\"")

        conversation_text = "\n".join(conversation_lines) if conversation_lines else "(대화 없음)"

        # 위험도에 따른 톤 가이드
        if total_suspicion >= 10:
            tone_guide = "극도의 긴장감. 몬스터들의 본성이 드러남. 플레이어를 향한 직접적 위협."
        elif total_suspicion >= 5:
            tone_guide = "불안한 분위기. 상냥함 뒤에 숨은 광기가 새어나옴."
        else:
            tone_guide = "표면적 평온. 하지만 뭔가 이상한 느낌이 감돈다."

        prompt = f"""당신은 공포 소설 작가입니다. 아래 대화를 바탕으로 몬스터 가족의 밤을 소설 형식으로 묘사하세요.

[시나리오: {scenario_title}]
[톤: {scenario_tone}]
[현재 턴: {turn}/{turn_limit}]
[플레이어 인간성: {humanity}/10]
[가족 의심도: {total_suspicion}]

[분위기 가이드]
{tone_guide}

[몬스터 가족의 대화]
{conversation_text}

[작성 지침]
1. 위 대화를 소설 형식으로 변환하세요.
2. 대화를 직접 인용하면서 서술을 붙이세요.
3. 화자의 표정, 목소리 톤, 분위기를 묘사하세요.
4. 공포와 긴장감을 살리세요.
5. 5~8문장으로 간결하게 작성하세요.

[출력]"""

        return prompt


# ============================================================
    # 엔딩 나레이션 전용 메서드 (EndingChecker에서 호출)
    # ============================================================
    def render_ending(
        self,
        ending_info: dict,
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        엔딩 나레이션 생성

        EndingChecker에서 엔딩이 판별되면 호출되어 epilogue_prompt를 기반으로
        드라마틱한 엔딩 텍스트를 생성합니다.

        Args:
            ending_info: 엔딩 정보 dict {ending_id, name, epilogue_prompt, on_enter_events}
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 엔딩 나레이션 텍스트
        """
        logger.info(f"Rendering ending: {ending_info.get('ending_id', 'unknown')}")

        # CUDA 사용 가능 여부로 LM 사용 결정
        import torch
        use_lm = self._enable_lm and torch.cuda.is_available()

        if use_lm:
            dialogue = self._render_with_lm_ending(ending_info, world_state, assets)
        else:
            dialogue = self._render_simple_ending(ending_info, world_state, assets)

        # 렌더 로그 기록
        self._render_log.append({
            "phase": "ending",
            "ending_id": ending_info.get("ending_id", ""),
            "ending_name": ending_info.get("name", ""),
            "dialogue_length": len(dialogue),
            "used_lm": use_lm,
        })

        logger.debug(f"Rendered ending dialogue: {len(dialogue)} chars")
        return dialogue

    def _render_simple_ending(
        self,
        ending_info: dict,
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        엔딩 단순 텍스트 조합 (non-CUDA 환경용)

        Args:
            ending_info: 엔딩 정보 dict
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 조합된 엔딩 텍스트
        """
        ending_id = ending_info.get("ending_id", "")
        ending_name = ending_info.get("name", "")
        epilogue_prompt = ending_info.get("epilogue_prompt", "")

        parts = []
        parts.append("=" * 40)
        parts.append("")
        parts.append(f"【 {ending_name} 】")
        parts.append("")

        # epilogue_prompt가 있으면 그것을 기반으로 간단한 엔딩 텍스트 구성
        if epilogue_prompt:
            # epilogue_prompt의 핵심 키워드를 활용한 간단한 서술
            parts.append(f"...{epilogue_prompt}...")
        else:
            # 기본 엔딩 텍스트
            parts.append("이야기가 끝났다.")

        parts.append("")

        # 상태 기반 추가 묘사
        humanity = world_state.vars.get("humanity", 10)
        turn = world_state.turn
        turn_limit = assets.get_turn_limit()

        if "escape" in ending_id.lower() or "탈출" in ending_name:
            parts.append("저택의 문이 열리고, 당신은 마침내 바깥 세계를 마주한다.")
        elif "death" in ending_id.lower() or "죽음" in ending_name:
            parts.append("어둠이 모든 것을 삼킨다.")
        elif "puppet" in ending_id.lower() or "인형" in ending_name:
            parts.append("더 이상 당신은 당신이 아니다.")
        elif "truth" in ending_id.lower() or "진실" in ending_name:
            parts.append("진실은 때때로 자유보다 무겁다.")
        else:
            if humanity <= 3:
                parts.append("결국, 당신은 이 집의 일부가 되었다.")
            elif turn >= turn_limit:
                parts.append("시간이 다했다. 모든 것이 끝났다.")
            else:
                parts.append("이것이 당신이 선택한 결말이다.")

        parts.append("")
        parts.append(f"[{turn}/{turn_limit}턴 - 인간성 {humanity}]")
        parts.append("")
        parts.append("=" * 40)

        return "\n".join(parts)

    def _render_with_lm_ending(
        self,
        ending_info: dict,
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        엔딩 LM을 사용한 소설 형식 텍스트 생성

        Args:
            ending_info: 엔딩 정보 dict
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: LM이 생성한 엔딩 텍스트
        """
        # 모델 로드 (첫 호출 시에만)
        self._load_lm_model()

        # 모델 로드 실패 시 단순 조합으로 폴백
        if self._model is None or self._tokenizer is None:
            logger.warning("LM model not available, falling back to simple composition")
            return self._render_simple_ending(ending_info, world_state, assets)

        # 프롬프트 구성
        prompt = self._build_ending_narrative_prompt(ending_info, world_state, assets)

        # LM 생성 (엔딩은 좀 더 긴 텍스트 허용)
        try:
            ending_name = ending_info.get("name", "")
            generated_text = self._generate_with_lm(prompt, max_new_tokens=600)

            # 엔딩 형식으로 포맷팅
            formatted = [
                "=" * 40,
                "",
                f"【 {ending_name} 】",
                "",
                generated_text,
                "",
                "=" * 40,
            ]
            return "\n".join(formatted)

        except Exception as e:
            import traceback
            logger.error(f"LM generation failed: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.warning("Falling back to simple composition")
            return self._render_simple_ending(ending_info, world_state, assets)

    def _build_ending_narrative_prompt(
        self,
        ending_info: dict,
        world_state: "WorldState",
        assets: ScenarioAssets,
    ) -> str:
        """
        엔딩 내러티브 생성 프롬프트 구성

        epilogue_prompt를 활용하여 드라마틱한 엔딩 텍스트를 생성하도록 유도합니다.

        Args:
            ending_info: 엔딩 정보 dict
            world_state: 현재 월드 상태
            assets: 시나리오 에셋

        Returns:
            str: 구성된 프롬프트
        """
        # 엔딩 정보
        ending_id = ending_info.get("ending_id", "")
        ending_name = ending_info.get("name", "")
        epilogue_prompt = ending_info.get("epilogue_prompt", "")

        # 시나리오 정보
        scenario_title = assets.scenario.get("title", "")
        scenario_genre = assets.scenario.get("genre", "")
        scenario_tone = assets.scenario.get("tone", "")

        # 상태 정보
        turn = world_state.turn
        turn_limit = assets.get_turn_limit()
        humanity = world_state.vars.get("humanity", 10)
        total_suspicion = world_state.vars.get("total_suspicion", 0)

        # 인벤토리 정보
        inventory = world_state.inventory if world_state.inventory else []
        inventory_text = ", ".join(inventory) if inventory else "(없음)"

        # NPC 상태 요약 (동적 스탯)
        npc_summary = []
        for npc_id, npc_state in world_state.npcs.items():
            npc_data = assets.get_npc_by_id(npc_id)
            npc_name = npc_data.get("name", npc_id) if npc_data else npc_id
            stats_str = ", ".join(f"{k} {v}" for k, v in npc_state.stats.items())
            npc_summary.append(f"- {npc_name}: {stats_str}" if stats_str else f"- {npc_name}: (스탯 없음)")
        npc_summary_text = "\n".join(npc_summary) if npc_summary else "(없음)"

        prompt = f"""당신은 {scenario_genre} 장르의 베테랑 소설 작가입니다.
지금까지의 이야기가 클라이맥스에 도달했습니다. 아래 정보를 바탕으로 감동적이고 몰입감 있는 엔딩을 작성하세요.

[시나리오: {scenario_title}]
[장르: {scenario_genre}]
[톤: {scenario_tone}]

[도달한 엔딩]
- 엔딩 ID: {ending_id}
- 엔딩 이름: {ending_name}

[플레이어 최종 상태]
- 경과 턴: {turn}/{turn_limit}
- 인간성: {humanity}/10
- 총 의심도: {total_suspicion}
- 소지품: {inventory_text}

[NPC 최종 상태]
{npc_summary_text}

[엔딩 지시문 (중요!)]
{epilogue_prompt}

[작성 지침]
1. 위의 '엔딩 지시문'을 충실히 반영하여 엔딩을 작성하세요.
2. 플레이어의 여정을 마무리하는 감정적 클라이맥스를 만드세요.
3. 시나리오의 장르와 톤에 맞는 문체를 사용하세요.
4. 5~10문장으로 간결하면서도 여운이 남는 엔딩을 작성하세요.
5. 열린 결말이나 암시적 표현을 활용해도 좋습니다.

[출력]"""

        return prompt


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
    from app.schemas import WorldState, NPCState

    print("=" * 60)
    print("NARRATIVE 컴포넌트 테스트")
    print("=" * 60)

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"\n[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 내러티브 레이어
    narrative = NarrativeLayer()

    # 테스트용 월드 상태
    world_state = WorldState(
        turn=3,
        npcs={"button_mother": NPCState(npc_id="button_mother", stats={"trust": 3, "fear": 0, "suspicion": 2})},
        vars={"humanity": 8, "total_suspicion": 2},
    )

    # 테스트 1: 이벤트만 있는 경우
    print(f"\n[2] 이벤트만 렌더링")
    print("-" * 40)

    event_description = ["피해자 가족이 고개를 끄덕인다.", "침묵이 흐른다."]
    state_delta = {}

    dialogue = narrative.render_day(
        event_description=event_description,
        state_delta=state_delta,
        world_state=world_state,
        assets=assets,
    )
    print(dialogue)

    # 테스트 2: 이벤트 + 상태 변화
    print(f"\n[3] 이벤트 + 상태 변화 렌더링")
    print("-" * 40)

    state_delta_with_changes = {
        "npcs": {
            "button_mother": {"trust": 2, "suspicion": 1}
        },
        "vars": {"humanity": -1}
    }

    dialogue_with_delta = narrative.render_day(
        event_description=["엄마의 눈빛이 날카로워진다.", "뭔가 수상하다는 듯이 바라본다."],
        state_delta=state_delta_with_changes,
        world_state=world_state,
        assets=assets,
    )
    print(dialogue_with_delta)

    # 테스트 3: 여러 이벤트 + 인벤토리 변화
    print(f"\n[4] 여러 이벤트 + 인벤토리 변화")
    print("-" * 40)

    state_delta_inventory = {
        "inventory_add": ["부엌칼"],
        "vars": {"knife_touched": 1}
    }

    dialogue_inventory = narrative.render_day(
        event_description=[
            "당신은 부엌을 둘러본다.",
            "서랍 안에서 날카로운 칼이 눈에 띈다.",
            "조심스럽게 칼을 집어든다."
        ],
        state_delta=state_delta_inventory,
        world_state=world_state,
        assets=assets,
    )
    print(dialogue_inventory)

    print("\n" + "=" * 60)
    print("NARRATIVE 테스트 완료")
    print("=" * 60)