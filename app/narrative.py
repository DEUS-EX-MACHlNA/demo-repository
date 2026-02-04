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
import os
import random
from typing import Any, Optional, TYPE_CHECKING

from dotenv import load_dotenv

from app.loader import ScenarioAssets

if TYPE_CHECKING:
    from app.models import WorldState

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
    # 밤 나레이션 전용 메서드 (GameLoop에서 호출)
    # ============================================================
    def render_night(
        self,
        world_snapshot: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[list[dict[str, str]]],
        extras: dict[str, Any] | None = None,
    ) -> str:
        """
        밤 페이즈 나레이션 생성 (GameLoop에서 호출)

        night_conversation을 받아서 몬스터 소설 형식으로 변환합니다.

        Args:
            world_snapshot: 현재 월드 상태
            assets: 시나리오 에셋
            night_conversation: 대화 리스트 [[{speaker, text}, ...], ...]
            extras: NightResult.extras (night_events, conversation_pairs 등)

        Returns:
            str: 몬스터 소설화된 밤 나레이션 텍스트
        """
        extras = extras or {}
        night_events = extras.get("night_events", [])
        conversation_pairs = extras.get("conversation_pairs", [])

        turn = world_snapshot.turn
        turn_limit = assets.get_turn_limit()
        tone = assets.scenario.get("tone", "")
        scenario_id = assets.scenario.get("id", "")

        # 만진 오브젝트 추출
        touched_objects = self._extract_touched_objects(world_snapshot)

        # 시나리오별 특수 처리
        if scenario_id == "coraline":
            return self._render_night_coraline(
                world_snapshot, assets, night_conversation, conversation_pairs,
                night_events, touched_objects, turn, turn_limit, tone
            )

        # 일반 밤 나레이션
        return self._render_night_generic(
            world_snapshot, assets, night_conversation, conversation_pairs,
            night_events, turn, turn_limit, tone
        )

    def _extract_touched_objects(self, world_snapshot: "WorldState") -> list[str]:
        """월드 상태에서 만진 오브젝트 목록 추출"""
        touched = []
        vars_ = world_snapshot.vars

        # 오브젝트 매핑 (코렐라인 등)
        object_map = {
            "knife_touched": "부엌칼",
            "match_touched": "성냥",
            "needle_touched": "바늘",
            "mirror_touched": "거울",
            "button_box_touched": "단추 상자",
            "photo_touched": "가족사진",
        }

        for var_name, object_name in object_map.items():
            if vars_.get(var_name):
                touched.append(object_name)

        return touched

    def _render_night_generic(
        self,
        world_snapshot: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[list[dict[str, str]]],
        conversation_pairs: list[tuple[str, str]],
        night_events: list[str],
        turn: int,
        turn_limit: int,
        tone: str,
    ) -> str:
        """일반 시나리오용 밤 나레이션"""
        event_text = "\n".join(f"- {e}" for e in night_events) if night_events else "- 특별한 사건 없음"

        # 대화 요약
        conv_summaries = []
        for i, conv in enumerate(night_conversation):
            if conv and i < len(conversation_pairs):
                npc1_id, npc2_id = conversation_pairs[i]
                n1 = (assets.get_npc_by_id(npc1_id) or {}).get("name", npc1_id)
                n2 = (assets.get_npc_by_id(npc2_id) or {}).get("name", npc2_id)
                last_line = conv[-1]["text"][:40] if conv else ""
                conv_summaries.append(f"{n1}과(와) {n2}: \"{last_line}...\"")

        conv_text = "\n".join(f"- {s}" for s in conv_summaries) if conv_summaries else "- 대화 없음"

        # LM 사용 가능하면 LM 생성
        if self._enable_lm:
            self._load_lm_model()
            if self._lm_model is not None:
                prompt = (
                    f"다음은 턴 {turn}/{turn_limit}의 밤에 일어난 일들입니다.\n\n"
                    f"사건:\n{event_text}\n\n"
                    f"대화:\n{conv_text}\n\n"
                    f"시나리오 톤: {tone}\n\n"
                    "이 내용을 바탕으로 분위기 있고 간결한 밤 내러티브를 2~3문장으로 작성하세요.\n\n"
                    "내러티브:"
                )
                try:
                    narrative = self._generate_with_lm(prompt, max_new_tokens=150)
                    if narrative:
                        return narrative.strip()
                except Exception as e:
                    logger.warning(f"LM generation failed: {e}")

        # Fallback
        return self._fallback_night_narrative(turn, turn_limit, night_events)

    def _render_night_coraline(
        self,
        world_snapshot: "WorldState",
        assets: ScenarioAssets,
        night_conversation: list[list[dict[str, str]]],
        conversation_pairs: list[tuple[str, str]],
        night_events: list[str],
        touched_objects: list[str] | None,
        turn: int,
        turn_limit: int,
        tone: str,
    ) -> str:
        """코렐라인 시나리오 전용 밤 나레이션 - 몬스터 소설화"""
        humanity = world_snapshot.vars.get("humanity", 10)
        total_suspicion = world_snapshot.vars.get("total_suspicion", 0)

        # 만진 오브젝트 텍스트
        touched_text = ", ".join(touched_objects) if touched_objects else "아무것도"

        # 대화에서 가장 섬뜩한 부분 추출 (소설화 재료)
        dialogue_highlights = self._extract_monstrous_dialogue(
            night_conversation, conversation_pairs, assets
        )

        # LM 사용
        if self._enable_lm:
            self._load_lm_model()
            if self._lm_model is not None:
                prompt = self._build_coraline_monster_prompt(
                    turn, turn_limit, humanity, total_suspicion,
                    touched_text, dialogue_highlights, night_events,
                    night_conversation, conversation_pairs, assets
                )
                try:
                    narrative = self._generate_with_lm(prompt, max_new_tokens=300)
                    if narrative:
                        return narrative.strip()
                except Exception as e:
                    logger.warning(f"Coraline night LM generation failed: {e}")

        # Fallback - 코렐라인 전용 몬스터 나레이션
        return self._fallback_coraline_monster(
            turn, humanity, total_suspicion, touched_objects,
            night_events, night_conversation, assets
        )

    def _extract_monstrous_dialogue(
        self,
        night_conversation: list[list[dict[str, str]]],
        conversation_pairs: list[tuple[str, str]],
        assets: ScenarioAssets,
    ) -> list[str]:
        """대화에서 가장 섬뜩한 부분 추출"""
        highlights = []

        # 몬스터 키워드 - 이 단어가 포함된 대사 우선 추출
        monster_keywords = [
            "처벌", "눈", "단추", "꿰매", "자르", "태우", "가둬", "혼나",
            "도망", "배신", "사랑", "가족", "영원히", "규칙", "봤다",
            "키키키", "후후후", "히히", "감히", "어디",
        ]

        for conv in night_conversation:
            for utt in conv:
                text = utt.get("text", "")
                speaker = utt.get("speaker", "")

                # 몬스터 키워드가 있으면 추가
                if any(kw in text for kw in monster_keywords):
                    highlights.append(f"{speaker}: \"{text}\"")
                # 마지막 2개 대사는 무조건 추가
                elif conv.index(utt) >= len(conv) - 2:
                    highlights.append(f"{speaker}: \"{text}\"")

        return highlights[:6]  # 최대 6개

    def _build_coraline_monster_prompt(
        self,
        turn: int,
        turn_limit: int,
        humanity: int,
        total_suspicion: int,
        touched_text: str,
        dialogue_highlights: list[str],
        night_events: list[str],
        night_conversation: list[list[dict[str, str]]],
        conversation_pairs: list[tuple[str, str]],
        assets: ScenarioAssets,
    ) -> str:
        """코렐라인 밤 나레이션 - 몬스터 소설화 프롬프트"""
        dialogue_text = "\n".join(dialogue_highlights) if dialogue_highlights else "(대화 없음)"
        events_text = "\n".join(f"- {e}" for e in night_events) if night_events else "(없음)"

        # 위험도에 따른 몬스터 톤
        if total_suspicion >= 12:
            tone_guide = """
[몬스터 톤: 최고 위험]
- 괴물의 본성이 드러남. 인간의 탈을 벗은 것들.
- "사랑"이라는 단어가 나올 때마다 공포가 배가됨
- 구체적인 신체 훼손 암시 (눈 꿰매기, 손가락 자르기)
- 플레이어를 향한 직접적 위협
- 탈출은 이제 불가능하다는 절망감"""
        elif total_suspicion >= 8:
            tone_guide = """
[몬스터 톤: 고위험]
- 상냥함 뒤에 숨은 광기가 새어나옴
- "걱정" "보호"라는 단어가 감금과 구속을 의미
- 가족끼리 서로 비난하며 히스테리
- 처벌 논의가 구체적으로"""
        else:
            tone_guide = """
[몬스터 톤: 불안]
- 표면은 평온, 내면은 썩어있음
- 달콤한 말투지만 눈빛은 차갑게
- 은밀한 감시, 속삭임
- "아직은" 참고 있다는 느낌"""

        return f"""당신은 공포 소설 작가입니다. 아래 대화를 바탕으로 "몬스터가 된 인형 가족"의 밤을 묘사하세요.

[세계관: 코렐라인 - 단추 눈의 저택]
플레이어는 단추 눈 인형 가족에게 갇힌 인간. 가족은 플레이어의 눈에 단추를 꿰매 영원히 함께하길 원한다.
이들의 "사랑"은 인간의 그것이 아니다. 소유욕, 집착, 광기다.

[현재 상황]
- 턴: {turn}/{turn_limit} (끝이 가까워질수록 더 위험)
- 플레이어 인간성: {humanity}/10 (0이 되면 인형이 됨)
- 가족 의심도: {total_suspicion} (높을수록 즉각적 위협)
- 오늘 만진 오브젝트: {touched_text}

[가족 회의에서 오간 대화]
{dialogue_text}

[밤의 사건들]
{events_text}
{tone_guide}

[작성 지침]
1. 3~5문장의 몬스터 소설 스타일로 작성
2. 대화 내용을 직접 인용하며 그 섬뜩함을 강조
3. 플레이어의 심리 묘사 (공포, 절망, 불안)
4. 감각적 묘사 (어둠, 발소리, 속삭임, 단추 눈의 번뜩임)
5. "사랑"이라는 단어가 나올 때 그것이 얼마나 뒤틀린 것인지 암시
6. 인형들의 비인간적 움직임/표정 묘사

[출력 - 몬스터 소설]"""

    def _fallback_night_narrative(
        self, turn: int, turn_limit: int, events: list[str]
    ) -> str:
        """일반 시나리오 fallback 나레이션"""
        if turn <= 3:
            base = random.choice([
                "하루가 저문다. 아직 시간은 있다.",
                "첫날 밤. 조각들이 서서히 모이기 시작한다.",
            ])
        elif turn <= 7:
            base = random.choice([
                "밤이 깊어간다. 진실과 조작의 경계가 흐려진다.",
                "시간이 흐른다. 당신의 질문들이 세계를 바꾸고 있다.",
            ])
        else:
            base = random.choice([
                "시간이 얼마 남지 않았다. 결론을 향해 달려가고 있다.",
                "밤공기가 무겁다. 끝이 가까워지고 있다.",
            ])

        if events:
            base += " " + events[0]
        return base

    def _fallback_coraline_monster(
        self,
        turn: int,
        humanity: int,
        total_suspicion: int,
        touched_objects: list[str] | None,
        events: list[str],
        night_conversation: list[list[dict[str, str]]],
        assets: ScenarioAssets,
    ) -> str:
        """코렐라인 시나리오 fallback - 몬스터 소설화"""
        parts = []

        # 대화에서 인용할 대사 추출
        quote = ""
        for conv in night_conversation:
            for utt in conv:
                text = utt.get("text", "")
                if any(kw in text for kw in ["처벌", "눈", "단추", "사랑", "가족"]):
                    quote = f"'{text[:30]}...'"
                    break
            if quote:
                break

        # 위험도별 몬스터 나레이션
        if total_suspicion >= 12:
            opening = random.choice([
                "문 앞에서 발소리가 멈췄다. 숨이 막힌다. 잠금장치가 딸깍거린다.",
                "어둠 속에서 단추 눈 세 쌍이 반짝인다. 그들이 들어온다. 천천히. 확신에 차서.",
                "엄마의 미소가 갈라진다. 입꼬리가 귀까지 찢어지듯 올라간다. '사랑하는 아가야...'",
            ])
            if quote:
                parts.append(f"{opening} {quote} 그 말이 머릿속에서 맴돈다.")
            else:
                parts.append(f"{opening} '이제 진짜 가족이 될 시간이야.'")

            parts.append(random.choice([
                "바늘이 촛불에 반짝인다. 실이 끝없이 풀려나온다. 검은 단추 두 개가 손바닥에서 데굴데굴 구른다.",
                "아빠가 천천히 가위를 든다. 찰칵. 찰칵. 공기를 자르는 소리가 심장을 찌른다.",
                "딸이 동요를 부른다. '영원히~ 영원히~ 같이 놀자~' 그 목소리에서 인간의 온기는 느껴지지 않는다.",
            ]))

        elif total_suspicion >= 8:
            opening = random.choice([
                "가족 회의가 끝났지만, 그들의 눈빛이 아직도 등 뒤에서 느껴진다.",
                "벽 너머에서 속삭임이 새어나온다. 네 이름이 들린다. 계속, 계속.",
                "'처벌'이라는 단어가 귓가에 맴돈다. 그들은 이미 결정을 내렸다.",
            ])
            if quote:
                parts.append(f"{opening} {quote}")
            else:
                parts.append(opening)

            parts.append(random.choice([
                "문 아래로 그림자가 지나간다. 왔다갔다. 밤새 그럴 것이다. 감시당하고 있다.",
                "엄마의 목소리가 달콤하게 속삭인다. '우리가 얼마나 걱정하는데...' 그 다정함이 끔찍하다.",
                "'규칙을 어기면...' 아빠의 저음이 울린다. 뒷말은 없었지만, 다 알고 있다.",
            ]))

        else:
            opening = random.choice([
                "밤이 깊다. 이 집의 밤은 유독 고요하다. 너무 고요해서 무섭다.",
                "그들이 나를 보는 눈빛. 단추인데 왜 이렇게 많은 것이 담겨 있을까.",
                "엄마가 저녁을 차려줬다. 정성스럽게. 사랑스럽게. 그래서 더 무섭다.",
            ])
            parts.append(opening)

            parts.append(random.choice([
                "언젠가 이 집의 진짜 모습을 보게 될 것이다. 아니, 이미 보고 있는지도 모른다.",
                "'우리 아가~' 엄마의 목소리가 꿀처럼 달콤하다. 파리를 유혹하는 끈끈이처럼.",
                "딸이 인형놀이를 하자고 한다. 인형의 눈에는 단추가 달려있다. 내 미래가 보인다.",
            ]))

        # 인간성에 따른 추가
        if humanity <= 3:
            parts.append("거울을 봤다. 내 눈이... 검게 변하고 있는 것 같다. 착각이었으면 좋겠다.")
        elif humanity <= 6:
            parts.append("손끝이 차갑다. 피부가 굳어가는 느낌. 점점 이 집에 동화되어 간다.")

        # 만진 오브젝트
        if touched_objects:
            if "부엌칼" in touched_objects:
                parts.append("숨겨둔 칼이 차갑게 심장을 누른다. 아직 기회는 있다. 있어야 한다.")
            if "성냥" in touched_objects:
                parts.append("호주머니의 성냥갑이 바스락거린다. 불. 인형의 유일한 천적.")
            if "거울" in touched_objects:
                parts.append("거울에서 본 내 모습이 자꾸 떠오른다. 아직... 아직 인간이야.")

        return " ".join(parts)

    def _fallback_coraline_night(
        self,
        turn: int,
        humanity: int,
        total_suspicion: int,
        touched_objects: list[str] | None,
        events: list[str],
    ) -> str:
        """코렐라인 시나리오 fallback 나레이션 (구버전 호환)"""
        parts = []

        # 기본 분위기
        if total_suspicion >= 12:
            parts.append(random.choice([
                "가족 회의가 끝났다. 그들의 눈에서 결의가 느껴진다. 오늘 밤... 뭔가 일어날 것 같다.",
                "단추 눈들이 어둠 속에서 번뜩인다. '더 이상 기다릴 필요 없어.' 아빠의 저음이 울린다.",
                "엄마의 미소가 굳어있다. '사랑하는 아가야... 이제 진짜 가족이 될 시간이야.'",
            ]))
        elif total_suspicion >= 8:
            parts.append(random.choice([
                "가족 회의의 대화가 계속 귓가에 맴돈다. '처벌'이라는 단어가 머리에서 떠나지 않는다.",
                "그들이 뭔가를 계획하고 있다. 밤새 발소리가 문 앞을 서성인다.",
                "'나쁜 아이는 혼나야 해~' 딸의 동요가 어둠 속에서 들려온다.",
            ]))
        else:
            parts.append(random.choice([
                "밤이 깊어간다. 벽 너머에서 속삭이는 소리가 들린다.",
                "가족의 시선이 느껴진다. 잠이 오지 않는다.",
                "어딘가에서 바느질 소리가 들린다. 찰칵... 찰칵...",
            ]))

        # 인간성에 따른 추가
        if humanity <= 3:
            parts.append("거울을 봤을 때... 네 눈이 단추처럼 보였던 건 착각이었을까?")
        elif humanity <= 6:
            parts.append("손끝이 차갑다. 점점 이 집에 익숙해지는 것 같다.")

        # 만진 오브젝트에 따른 추가
        if touched_objects:
            if "부엌칼" in touched_objects or "칼" in touched_objects:
                parts.append("숨겨둔 칼이 차갑게 느껴진다. 그들이 알고 있을까?")
            if "성냥" in touched_objects or "불" in touched_objects:
                parts.append("성냥갑이 호주머니에서 바스락거린다. 불... 인형의 천적.")
            if "거울" in touched_objects:
                parts.append("거울에서 본 네 모습이 자꾸 떠오른다. 아직... 인간이야.")

        return " ".join(parts)


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
