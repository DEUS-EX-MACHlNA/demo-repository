"""
app/parser.py
Prompt Parser (2단계 구현: Rule-based → LM-based)

사용자 입력을 분석하여 intent, target_npc_id, item_id를 추출합니다.

## 파싱 전략 (2단계)

1. **Rule-based 추출**:
   - NPC/아이템 aliases 매칭 (assets에서 로드)
   - 지시대명사 패턴 ("아까 걔", "다시 사용" 등) → last_mentioned_npc_id / last_used_item_id 활용

2. **LM-based 추출** (Rule-based 실패 시):
   - 작은 LM 모델 (EXAONE-3.5-2.4B-Instruct) 호출
   - 환경변수 HF_TOKEN 필요

## 하위 호환성

ParsedInput.target property:
- 기존 코드: `parsed.target` 그대로 사용 가능
- 새 코드: `parsed.target_npc_id`, `parsed.item_id` 명확하게 구분
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from app.loader import ScenarioAssets
from app.models import Intent, ParsedInput, WorldState

logger = logging.getLogger(__name__)


class PromptParser:
    """
    유저 입력을 파싱하여 ParsedInput을 생성하는 2단계 파서

    1. Rule-based: aliases 매칭 + 지시대명사 패턴
    2. LM-based: 작은 LM 모델 호출 (EXAONE-3.5-2.4B-Instruct)
    """

    # 의도 감지를 위한 키워드 패턴
    INTENT_PATTERNS = {
        Intent.LEADING: [
            r"그러니까.*맞(지|죠|잖아)",
            r"분명히",
            r"확실히",
            r"틀림없이",
            r"아닌가요\?",
            r"그렇지\?",
            r"맞지\?",
            r"~인 거야",
            r"~한 거 아니야",
        ],
        Intent.EMPATHIC: [
            r"힘드(시|셨)",
            r"어려우셨",
            r"이해(해요|합니다)",
            r"공감",
            r"그랬군요",
            r"안타깝",
            r"걱정",
            r"위로",
            r"괜찮",
        ],
        Intent.SUMMARIZE: [
            r"정리하면",
            r"요약하면",
            r"결론적으로",
            r"따라서",
            r"즉,",
            r"다시 말해",
            r"종합하면",
            r"확정",
        ],
        Intent.NEUTRAL: [
            r"언제",
            r"어디",
            r"누구",
            r"무엇",
            r"어떻게",
            r"왜",
            r"\?$",
        ],
    }

    # 지시대명사 패턴 (NPC)
    NPC_REFERENCE_PATTERNS = [
        r"아까\s*(걔|그\s*사람|그\s*분)",
        r"^(걔|너|당신|그\s*사람|그\s*분)",
        r"(다시|또)\s*(물어|질문|대화)",
    ]

    # 지시대명사 패턴 (아이템)
    ITEM_REFERENCE_PATTERNS = [
        r"(다시|또)\s*(사용|써|쓰|확인)",
        r"(아까|방금)\s*(그|사용한|쓴)\s*(거|것|아이템)",
    ]

    def __init__(self, enable_lm: bool = True):
        """
        파서 초기화

        Args:
            enable_lm: LM 기반 추출 활성화 여부 (기본: True)
        """
        self._compiled_patterns: dict[Intent, list[re.Pattern]] = {}
        self._compile_patterns()

        # 지시대명사 패턴 컴파일
        self._npc_ref_patterns = [re.compile(p, re.IGNORECASE) for p in self.NPC_REFERENCE_PATTERNS]
        self._item_ref_patterns = [re.compile(p, re.IGNORECASE) for p in self.ITEM_REFERENCE_PATTERNS]

        # LM 모델 (lazy loading)
        self._enable_lm = enable_lm
        self._lm_model = None
        self._lm_tokenizer = None
        self._lm_loaded = False

    def _compile_patterns(self):
        """정규식 패턴 미리 컴파일"""
        for intent, patterns in self.INTENT_PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def _load_lm_model(self):
        """LM 모델 로드 (lazy loading)"""
        if self._lm_loaded:
            return

        if not self._enable_lm:
            logger.info("LM-based extraction is disabled")
            self._lm_loaded = True
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model_name = "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct"
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
            logger.warning("Falling back to stub.")
            self._lm_loaded = True
            self._lm_model = None
            self._lm_tokenizer = None

    def _detect_intent(self, user_input: str) -> Intent:
        """
        텍스트에서 의도 감지 (Rule-based)
        """
        priority_order = [Intent.LEADING, Intent.SUMMARIZE, Intent.EMPATHIC, Intent.NEUTRAL]

        for intent in priority_order:
            patterns = self._compiled_patterns.get(intent, [])
            for pattern in patterns:
                if pattern.search(user_input):
                    logger.debug(f"Intent detected: {intent.value} (pattern: {pattern.pattern})")
                    return intent

        return Intent.UNKNOWN

    def _extract_npc_aliases(self, assets: ScenarioAssets) -> dict[str, list[str]]:
        """assets에서 NPC aliases 추출"""
        npc_aliases = {}
        for npc in assets.npcs.get("npcs", []):
            npc_id = npc.get("npc_id")
            if not npc_id:
                continue

            aliases = []
            # name
            if npc.get("name"):
                aliases.append(npc["name"])
            # aliases 필드
            if npc.get("aliases"):
                aliases.extend(npc["aliases"])

            npc_aliases[npc_id] = aliases

        return npc_aliases

    def _extract_item_aliases(self, assets: ScenarioAssets) -> dict[str, list[str]]:
        """assets에서 item aliases 추출"""
        item_aliases = {}
        for item in assets.items.get("items", []):
            item_id = item.get("item_id")
            if not item_id:
                continue

            aliases = []
            # name
            if item.get("name"):
                aliases.append(item["name"])
            # aliases 필드
            if item.get("aliases"):
                aliases.extend(item["aliases"])

            item_aliases[item_id] = aliases

        return item_aliases

    def _normalize_text(self, text: str) -> str:
        """텍스트 정규화: 소문자 변환 + 공백 제거 + 조사 제거"""
        # 소문자 변환 + 공백 제거
        normalized = text.lower().replace(" ", "")

        # 한국어 조사 제거 (뒤에서부터 매칭)
        # 우선순위: 긴 조사부터 제거 (예: "에게서" 먼저, "에게" 나중)
        particles = [
            "에게서", "한테서", "으로부터", "로부터",  # 3-4글자 조사
            "에게", "한테", "께서", "에서", "으로", "로써", "부터", "까지", "마저", "조차",  # 2글자 조사
            "은", "는", "이", "가", "을", "를", "의", "와", "과", "에", "로", "도", "만", "야"  # 1글자 조사
        ]

        for particle in particles:
            if normalized.endswith(particle):
                # 조사를 제거한 후 최소 2글자 이상 남아야 함 (예: "가을" → "가" 방지)
                candidate = normalized[:-len(particle)]
                if len(candidate) >= 2:
                    normalized = candidate
                    break  # 하나만 제거

        return normalized

    def _alias_matches(self, alias: str, user_input: str) -> bool:
        """
        alias가 user_input에 포함되어 있는지 확인 (띄어쓰기 무시 + 조사 제거)

        - 원본 그대로 매칭
        - 소문자 변환 후 매칭
        - 공백 제거 후 매칭
        - 조사 제거 후 매칭 ("파트너에게" → "파트너")
        """
        # 원본 매칭
        if alias in user_input:
            return True

        # 소문자 매칭
        alias_lower = alias.lower()
        user_input_lower = user_input.lower()
        if alias_lower in user_input_lower:
            return True

        # 공백 제거 후 매칭
        alias_normalized = self._normalize_text(alias)
        user_input_normalized = self._normalize_text(user_input)
        if alias_normalized in user_input_normalized:
            return True

        # 조사 제거 매칭: user_input의 각 단어에서 조사를 제거하고 alias와 비교
        # 예: "파트너에게" → "파트너" 추출 후 alias와 비교
        import re
        # 공백이나 구두점으로 분리된 단어들 추출
        words = re.findall(r'[\w가-힣]+', user_input)
        for word in words:
            word_normalized = self._normalize_text(word)
            if word_normalized == alias_normalized:
                return True

        return False

    def _extract_target_npc_ids_rule_based(
        self,
        user_input: str,
        assets: ScenarioAssets,
        world_snapshot: WorldState
    ) -> list[str]:
        """
        Rule-based NPC ID 추출 (여러 개 가능)

        1. aliases 매칭 (여러 개 추출 가능)
        2. 지시대명사 패턴 → last_mentioned_npc_id
        3. 실패 시 빈 리스트 반환
        """
        found_npcs = []

        # 1. aliases 매칭 (모든 매칭되는 NPC 추출)
        npc_aliases = self._extract_npc_aliases(assets)
        for npc_id, aliases in npc_aliases.items():
            for alias in aliases:
                if self._alias_matches(alias, user_input):
                    # assets에서 NPC 존재 확인
                    if assets.get_npc_by_id(npc_id) and npc_id not in found_npcs:
                        logger.debug(f"NPC detected via alias: {npc_id} (alias: {alias})")
                        found_npcs.append(npc_id)
                        break  # 같은 NPC의 다른 alias는 스킵

        # 2. aliases로 찾지 못했다면 지시대명사 패턴 확인
        if not found_npcs:
            for pattern in self._npc_ref_patterns:
                if pattern.search(user_input):
                    last_npc_id = world_snapshot.vars.get("last_mentioned_npc_id", "")
                    if last_npc_id:
                        logger.debug(f"NPC detected via reference pattern: {last_npc_id}")
                        found_npcs.append(last_npc_id)
                        break

        return found_npcs

    def _extract_item_id_rule_based(
        self,
        user_input: str,
        assets: ScenarioAssets,
        world_snapshot: WorldState
    ) -> Optional[str]:
        """
        Rule-based item ID 추출

        1. aliases 매칭 (인벤토리에 있는 것만)
        2. 지시대명사 패턴 → last_used_item_id
        3. 실패 시 None 반환
        """
        # 1. aliases 매칭 (인벤토리에 있는 것만)
        item_aliases = self._extract_item_aliases(assets)
        for item_id, aliases in item_aliases.items():
            if item_id not in world_snapshot.inventory:
                continue  # 소유하지 않은 아이템은 스킵

            for alias in aliases:
                if self._alias_matches(alias, user_input):
                    logger.debug(f"Item detected via alias: {item_id} (alias: {alias})")
                    return item_id

        # 2. 지시대명사 패턴
        for pattern in self._item_ref_patterns:
            if pattern.search(user_input):
                last_item_id = world_snapshot.vars.get("last_used_item_id", "")
                if last_item_id and last_item_id in world_snapshot.inventory:
                    logger.debug(f"Item detected via reference pattern: {last_item_id}")
                    return last_item_id

        # 3. 실패
        return None

    def _call_lm(self, prompt: str, max_new_tokens: int = 64) -> str:
        """LM 모델 호출"""
        if not self._lm_model or not self._lm_tokenizer:
            return ""

        try:
            messages = [{"role": "user", "content": prompt}]
            input_ids = self._lm_tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt"
            ).to(self._lm_model.device)

            # attention_mask 생성 (pad token과 eos token이 같을 때 필요)
            attention_mask = (input_ids != self._lm_tokenizer.pad_token_id).long().to(self._lm_model.device)

            outputs = self._lm_model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.3,
                top_p=0.9,
                pad_token_id=self._lm_tokenizer.eos_token_id
            )

            response = self._lm_tokenizer.decode(outputs[0], skip_special_tokens=True)

            # 프롬프트 부분 제거
            if "[|assistant|]" in response:
                response = response.split("[|assistant|]")[-1].strip()

            return response

        except Exception as e:
            logger.error(f"LM call failed: {e}")
            return ""

    def _extract_target_npc_ids_lm_based(
        self,
        user_input: str,
        assets: ScenarioAssets,
        world_snapshot: WorldState
    ) -> list[str]:
        """
        LM-based NPC ID 추출 (여러 개 가능)
        """
        logger.debug("LM-based NPC extraction called")

        # LM 모델 로드 (lazy loading)
        self._load_lm_model()

        if not self._lm_model:
            # Fallback: 빈 리스트 반환
            return []

        # NPC 정보 구성
        npc_aliases = self._extract_npc_aliases(assets)
        npc_info = []
        for npc_id, aliases in npc_aliases.items():
            npc = assets.get_npc_by_id(npc_id)
            if npc:
                npc_info.append(f"- {npc_id}: {', '.join(aliases)}")

        npc_list_str = "\n".join(npc_info) if npc_info else "(없음)"

        # 최근 언급된 NPC 정보
        last_npc_id = world_snapshot.vars.get("last_mentioned_npc_id", "")
        last_npc_hint = f"\n최근 대화한 NPC: {last_npc_id}" if last_npc_id else ""

        # 프롬프트 구성 (여러 개 추출 가능하도록 수정)
        prompt = f"""다음 사용자 입력에서 대화 대상 NPC의 ID를 추출하세요.

사용자 입력: "{user_input}"

가능한 NPC 목록:
{npc_list_str}

최근 대화 NPC:
{last_npc_hint}

여러 NPC가 언급되었다면 쉼표로 구분하여 모두 반환하세요.
대화 대상 NPC가 없으면 "none"을 반환하세요.
NPC ID만 반환하세요 (추가 설명 없이).

NPC ID:"""

        response = self._call_lm(prompt, max_new_tokens=64)

        # 응답 파싱 (여러 개 추출)
        response = response.strip().lower()
        found_npcs = []
        for npc_id in npc_aliases.keys():
            if npc_id in response:
                logger.debug(f"LM-based NPC extraction: {npc_id}")
                found_npcs.append(npc_id)

        return found_npcs

    def _extract_item_id_lm_based(
        self,
        user_input: str,
        assets: ScenarioAssets,
        world_snapshot: WorldState
    ) -> Optional[str]:
        """
        LM-based item ID 추출
        """
        logger.debug("LM-based item extraction called")

        # LM 모델 로드 (lazy loading)
        self._load_lm_model()

        if not self._lm_model:
            # Fallback: None 반환
            return None

        # 아이템 정보 구성 (인벤토리에 있는 것만)
        item_aliases = self._extract_item_aliases(assets)
        item_info = []
        for item_id, aliases in item_aliases.items():
            if item_id in world_snapshot.inventory:
                item_info.append(f"- {item_id}: {', '.join(aliases)}")

        item_list_str = "\n".join(item_info) if item_info else "(없음)"

        # 최근 사용한 아이템 정보
        last_item_id = world_snapshot.vars.get("last_used_item_id", "")
        last_item_hint = f"\n최근 사용한 아이템: {last_item_id}" if last_item_id and last_item_id in world_snapshot.inventory else ""

        # 프롬프트 구성
        prompt = f"""다음 사용자 입력에서 사용하려는 아이템의 ID를 추출하세요.

사용자 입력: "{user_input}"

인벤토리에 있는 아이템 목록:
{item_list_str}

최근 사용 아이템:
{last_item_hint}

사용하려는 아이템이 명확하지 않으면 "none"을 반환하세요.
아이템 ID만 반환하세요 (추가 설명 없이).

아이템 ID:"""

        response = self._call_lm(prompt, max_new_tokens=32)

        # 응답 파싱
        response = response.strip().lower()
        for item_id in item_aliases.keys():
            if item_id in world_snapshot.inventory and item_id in response:
                logger.debug(f"LM-based item extraction: {item_id}")
                return item_id

        return None

    def _extract_content(self, user_input: str) -> str:
        """
        원본 텍스트에서 핵심 내용 추출

        TODO: 실제 LLM 호출로 대체
        """
        # Stub: 원본 텍스트를 그대로 반환 (간단한 정제만)
        content = user_input.strip()
        # 과도한 공백 제거
        content = re.sub(r"\s+", " ", content)
        return content

    def parse(
        self,
        user_input: str,
        target_npc_id: str = "",
        item_id: str = "",
        assets: Optional[ScenarioAssets] = None,
        world_snapshot: Optional[WorldState] = None
    ) -> ParsedInput:
        """
        유저 입력을 파싱하여 ParsedInput 반환 (2단계 전략)

        Args:
            user_input: 사용자 입력 텍스트 (필수)
            target_npc_id: 타겟 NPC ID (미리 지정 가능, ""이면 추출) - 하위 호환성
            item_id: 타겟 아이템 ID (미리 지정 가능, ""이면 추출)
            assets: 시나리오 에셋 (추출 시 필요)
            world_snapshot: 현재 월드 상태 (추출 시 필요)

        Returns:
            ParsedInput: 파싱 결과
        """
        logger.info(f"Parsing input: '{user_input[:50]}...'")

        # 각 추출의 방법을 독립적으로 추적
        npc_extraction_method = "prespecified"
        item_extraction_method = "prespecified"

        # Intent 감지 (항상 수행)
        intent = self._detect_intent(user_input)

        # target_npc_ids 추출 (미리 지정되지 않았으면)
        target_npc_ids = [target_npc_id] if target_npc_id else []

        if not target_npc_ids and assets and world_snapshot:
            # 1. Rule-based 추출
            target_npc_ids_extracted = self._extract_target_npc_ids_rule_based(
                user_input, assets, world_snapshot
            )

            if target_npc_ids_extracted:
                npc_extraction_method = "rule_based"
                target_npc_ids = target_npc_ids_extracted
            else:
                # 2. Rule-based 실패 시 LM-based 호출
                target_npc_ids_extracted = self._extract_target_npc_ids_lm_based(
                    user_input, assets, world_snapshot
                )
                if target_npc_ids_extracted:
                    npc_extraction_method = "lm_based"
                    target_npc_ids = target_npc_ids_extracted

        # item_id 추출 (미리 지정되지 않았으면) - NPC와 독립적으로 작동
        if not item_id and assets and world_snapshot:
            # 1. Rule-based 추출
            item_id_extracted = self._extract_item_id_rule_based(
                user_input, assets, world_snapshot
            )

            if item_id_extracted:
                item_extraction_method = "rule_based"
                item_id = item_id_extracted
            else:
                # 2. Rule-based 실패 시 LM-based 호출
                item_id_extracted = self._extract_item_id_lm_based(
                    user_input, assets, world_snapshot
                )
                if item_id_extracted:
                    item_extraction_method = "lm_based"
                    item_id = item_id_extracted

        # NPC나 아이템 중 하나라도 비어있으면 LM 추가 호출 (2차 보강)
        if assets and world_snapshot:
            if not target_npc_ids and npc_extraction_method != "prespecified":
                logger.debug("Empty NPC list - trying LM extraction as fallback")
                target_npc_ids_lm = self._extract_target_npc_ids_lm_based(
                    user_input, assets, world_snapshot
                )
                if target_npc_ids_lm:
                    target_npc_ids = target_npc_ids_lm
                    npc_extraction_method = "lm_based"

            if not item_id and item_extraction_method != "prespecified":
                logger.debug("Empty item_id - trying LM extraction as fallback")
                item_id_lm = self._extract_item_id_lm_based(
                    user_input, assets, world_snapshot
                )
                if item_id_lm:
                    item_id = item_id_lm
                    item_extraction_method = "lm_based"

        # extraction_method 결정 (우선순위: lm_based > rule_based > prespecified)
        # NPC와 아이템 중 더 높은 우선순위 방법 선택
        extraction_methods = [npc_extraction_method, item_extraction_method]
        if "lm_based" in extraction_methods:
            extraction_method = "lm_based"
        elif "rule_based" in extraction_methods:
            extraction_method = "rule_based"
        else:
            extraction_method = "prespecified"

        # content 추출
        content = self._extract_content(user_input)

        parsed = ParsedInput(
            intent=intent.value,
            target_npc_ids=target_npc_ids,
            item_id=item_id or "",
            content=content,
            raw=user_input,
            extraction_method=extraction_method
        )

        logger.info(
            f"Parsed result: intent={parsed.intent}, "
            f"target_npc_ids={parsed.target_npc_ids}, "
            f"item_id={parsed.item_id}, "
            f"method={parsed.extraction_method}"
        )
        return parsed

    def get_debug_info(self, parsed: ParsedInput) -> dict:
        """파싱 결과에 대한 디버그 정보 반환"""
        return {
            "parser": "two_stage_parser",
            "intent": parsed.intent,
            "target_npc_ids": parsed.target_npc_ids,
            "target_npc_id": parsed.target_npc_id,  # 하위 호환성
            "item_id": parsed.item_id,
            "extraction_method": parsed.extraction_method,
            "content_length": len(parsed.content),
            "raw_length": len(parsed.raw),
            "lm_loaded": self._lm_loaded,
            "lm_enabled": self._enable_lm,
        }


# ============================================================
# 모듈 레벨 인스턴스 (싱글턴 패턴)
# ============================================================
_parser_instance: Optional[PromptParser] = None


def get_parser() -> PromptParser:
    """
    PromptParser 싱글턴 인스턴스 반환

    Production 환경에서는 LM 기능이 활성화됩니다.
    Rule-based 추출 실패 시 LM-based 추출이 2차 게이트로 작동합니다.
    """
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = PromptParser(enable_lm=True)  # LM 활성화 (2차 게이트)
    return _parser_instance


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    from pathlib import Path
    from app.loader import ScenarioLoader
    from app.models import WorldState, NPCState
    from dotenv import load_dotenv

    load_dotenv("../.env")

    print("=" * 80)
    print("PARSER 컴포넌트 테스트 (2단계 파싱: Rule-based → LM-based)")
    print("=" * 80)
    print()
    print("## 파싱 전략")
    print()
    print("1. **Rule-based 추출**:")
    print("   - NPC/아이템 aliases 매칭 (assets에서 로드)")
    print("   - 지시대명사 패턴 (\"아까 걔\", \"다시 사용\" 등)")
    print("   - last_mentioned_npc_id / last_used_item_id 활용")
    print()
    print("2. **LM-based 추출** (Rule-based 실패 시):")
    print("   - 작은 LM 모델 (EXAONE-3.5-2.4B-Instruct) 호출")
    print("   - 환경변수 HF_TOKEN 필요 (없으면 LM 비활성화)")
    print()
    print("## 하위 호환성")
    print()
    print("ParsedInput.target property:")
    print("  - 기존 코드: `parsed.target` 그대로 사용 가능")
    print("  - 새 코드: `parsed.target_npc_id`, `parsed.item_id` 명확하게 구분")
    print()
    print("=" * 80)
    print()

    # 에셋 로드
    base_path = Path(__file__).parent.parent / "scenarios"
    loader = ScenarioLoader(base_path)
    scenarios = loader.list_scenarios()

    if not scenarios:
        print("[X] 시나리오가 없습니다!")
        exit(1)

    assets = loader.load(scenarios[0])
    print(f"[1] 시나리오 로드됨: {assets.scenario.get('title')}")

    # 테스트용 월드 상태 생성
    world = WorldState(
        turn=3,
        npcs={
            "family": NPCState(npc_id="family", trust=2, fear=0, suspicion=0),
            "partner": NPCState(npc_id="partner", trust=1, fear=0, suspicion=2),
        },
        inventory=["casefile_brief", "pattern_analyzer", "memo_pad"],
        vars={
            "clue_count": 2,
            "identity_match_score": 1,
            "fabrication_score": 1,
            "last_mentioned_npc_id": "family",
            "last_used_item_id": "pattern_analyzer"
        }
    )
    print(f"[2] 테스트 월드 상태 생성됨")
    print(f"    - last_mentioned_npc_id: {world.vars['last_mentioned_npc_id']}")
    print(f"    - last_used_item_id: {world.vars['last_used_item_id']}")
    print()

    # 파서 생성 (기본: LM 비활성화, Rule-based만 사용)
    parser = PromptParser(enable_lm=False)
    print(f"[3] 파서 생성됨 (LM 활성화: {parser._enable_lm})")
    if not parser._enable_lm:
        print("    [참고] LM 기능 비활성화 (Rule-based 파싱만 사용)")
        print("    [참고] LM을 활성화하려면: PromptParser(enable_lm=True)")
    print()

    # 사전 정의된 테스트 케이스
    print("=" * 80)
    print("사전 정의된 테스트 케이스 실행")
    print("=" * 80)
    print()

    test_cases = [
        ("피해자 가족에게 그날 무슨 일이 있었는지 물어본다", "", ""),
        ("그러니까 범인은 그 시간에 현장에 있었던 거 맞지?", "", ""),
        ("아까 걔한테 다시 물어본다", "", ""),  # 지시대명사 → last_mentioned_npc_id
        ("패턴 분석기를 사용해서 내 질문 패턴을 확인한다", "", ""),
        ("다시 사용해봐", "", ""),  # 지시대명사 → last_used_item_id
        ("정리하면, 목격자는 세 명이고 모두 같은 증언을 했다", "", ""),
    ]

    for i, (text, pre_npc_id, pre_item_id) in enumerate(test_cases, 1):
        print(f"[테스트 {i}]")
        print(f"  입력: \"{text}\"")

        parsed = parser.parse(text, pre_npc_id, pre_item_id, assets, world)

        # 추출 방법 표시
        extraction_stage = {
            "prespecified": "사전 지정",
            "rule_based": "1차 (Rule-based)",
            "lm_based": "2차 (LM-based)"
        }.get(parsed.extraction_method, parsed.extraction_method)

        print(f"  결과:")
        print(f"    - intent: {parsed.intent}")
        print(f"    - target_npc_ids: {parsed.target_npc_ids if parsed.target_npc_ids else '[]'}")
        print(f"    - item_id: {parsed.item_id or '(없음)'}")
        print(f"    - 추출 방법: {extraction_stage}")
        print()

    # 사용자 인터랙티브 모드
    print("=" * 80)
    print("사용자 입력 테스트 모드")
    print("=" * 80)
    print()
    print("직접 사용자 입력을 테스트해보세요.")
    print()
    print("특수 명령어:")
    print("  /set_npc <npc_id>   - 최근 언급 NPC 변경 (예: /set_npc family)")
    print("  /set_item <item_id> - 최근 사용 아이템 변경 (예: /set_item memo_pad)")
    print("  /show               - 현재 월드 상태 표시")
    print("  /help               - 도움말")
    print("  exit, quit, 종료    - 테스트 종료")
    print()

    while True:
        try:
            user_input = input("사용자 입력> ").strip()

            if not user_input:
                continue

            # 특수 명령어 처리
            if user_input.lower() in ["exit", "quit", "종료", "q"]:
                print("테스트 종료")
                break

            if user_input.lower() == "/help":
                print("특수 명령어:")
                print("  /set_npc <npc_id>   - 최근 언급 NPC 변경")
                print("  /set_item <item_id> - 최근 사용 아이템 변경")
                print("  /show               - 현재 월드 상태 표시")
                print("  exit, quit          - 테스트 종료")
                print()
                continue

            if user_input.lower() == "/show":
                print(f"현재 월드 상태:")
                print(f"  - turn: {world.turn}")
                print(f"  - last_mentioned_npc_id: {world.vars.get('last_mentioned_npc_id', '(없음)')}")
                print(f"  - last_used_item_id: {world.vars.get('last_used_item_id', '(없음)')}")
                print(f"  - npcs: {list(world.npcs.keys())}")
                print(f"  - inventory: {world.inventory}")
                print()
                continue

            if user_input.lower().startswith("/set_npc "):
                npc_id = user_input[9:].strip()
                if npc_id in world.npcs:
                    world.vars["last_mentioned_npc_id"] = npc_id
                    print(f"[OK] last_mentioned_npc_id를 '{npc_id}'로 변경했습니다.")
                else:
                    print(f"[X] NPC '{npc_id}'를 찾을 수 없습니다. 가능한 NPC: {list(world.npcs.keys())}")
                print()
                continue

            if user_input.lower().startswith("/set_item "):
                item_id = user_input[10:].strip()
                if item_id in world.inventory:
                    world.vars["last_used_item_id"] = item_id
                    print(f"[OK] last_used_item_id를 '{item_id}'로 변경했습니다.")
                else:
                    print(f"[X] 아이템 '{item_id}'가 인벤토리에 없습니다. 인벤토리: {world.inventory}")
                print()
                continue

            # 일반 파싱
            parsed = parser.parse(user_input, "", "", assets, world)

            # 추출 방법 표시
            extraction_stage = {
                "prespecified": "사전 지정",
                "rule_based": "1차 (Rule-based)",
                "lm_based": "2차 (LM-based)"
            }.get(parsed.extraction_method, parsed.extraction_method)

            print(f"  결과:")
            print(f"    - intent: {parsed.intent}")
            print(f"    - target_npc_ids: {parsed.target_npc_ids if parsed.target_npc_ids else '[]'}")
            print(f"    - item_id: {parsed.item_id or '(없음)'}")
            print(f"    - 추출 방법: {extraction_stage}")
            print()

        except KeyboardInterrupt:
            print("\n테스트 종료")
            break
        except Exception as e:
            print(f"[오류] {e}")
            print()

    print()
    print("=" * 80)
    print("[OK] PARSER 테스트 완료")
    print("=" * 80)
