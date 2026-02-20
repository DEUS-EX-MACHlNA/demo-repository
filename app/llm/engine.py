"""
app/llm/engine.py
통합 LLM 엔진 - LangChain 및 Transformers 백엔드 지원
"""
from __future__ import annotations

import os
import httpx
import logging
from typing import Any, Optional

from .config import (
    DEFAULT_BACKEND,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_REPETITION_PENALTY,
    get_model_config,
    get_adapter_model,
)

logger = logging.getLogger(__name__)

_instance: Optional[UnifiedLLMEngine] = None

# 중국어 유니코드 범위
_CHINESE_UNICODE_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
    (0x20000, 0x2A6DF), # CJK Unified Ideographs Extension B
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
]


def _is_chinese_char(char: str) -> bool:
    cp = ord(char)
    return any(start <= cp <= end for start, end in _CHINESE_UNICODE_RANGES)


class ChineseBlockingLogitsProcessor:
    """중국어 토큰 생성을 차단하는 LogitsProcessor (transformers 전용)"""

    def __init__(self, tokenizer):
        self._chinese_token_ids = self._find_chinese_token_ids(tokenizer)
        logger.info(f"중국어 차단 토큰 수: {len(self._chinese_token_ids)}")

    def _find_chinese_token_ids(self, tokenizer) -> list:
        vocab = tokenizer.get_vocab()
        chinese_ids = []
        for token, token_id in vocab.items():
            decoded = tokenizer.convert_tokens_to_string([token])
            if any(_is_chinese_char(c) for c in decoded):
                chinese_ids.append(token_id)
        return chinese_ids

    def __call__(self, input_ids, scores):
        if self._chinese_token_ids:
            scores[:, self._chinese_token_ids] = -float("inf")
        return scores


class UnifiedLLMEngine:
    """통합 LLM 엔진 - 다양한 백엔드 지원"""

    def __init__(
        self,
        backend: str = DEFAULT_BACKEND,
        model_name: str | None = None,
        **kwargs,
    ):
        """
        Args:
            backend: "vLLM" 또는 "transformers"
            model_name: 사용할 모델 (None이면 config에서 로드)
            **kwargs: 백엔드별 추가 설정
        """
        self.backend = backend
        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._model_name = model_name
        
        # 설정 로드
        self.config = get_model_config(backend)
        if not self._model_name:
            if backend == "vLLM":
                self._model_name = self.config["model"]
            else:
                self._model_name = self.config["model_name"]

        # 추가 설정 병합
        self.config.update(kwargs)

        # vLLM용 설정
        if self.backend == "vLLM":
            self.base_url = self.config["base_url"]
            self.api_key = self.config["api_key"]
            self._client = httpx.Client(timeout=httpx.Timeout(60.0))

            # debugging 용
            logger.info(self.api_key)
            logger.warning(self.base_url)
            logger.warning(self._model_name)



        logger.info(f"UnifiedLLMEngine 초기화: backend={backend}, model={self._get_model_name()}")

    def _get_model_name(self) -> str:
        """현재 모델 이름 반환"""
        if self.backend == "vLLM":
            return self.config.get("model", "unknown")
        else:
            return self.config.get("model_name", "unknown")

    def _load_model(self) -> None:
        """모델 로드 (lazy loading)"""
        if self._loaded:
            return
        self._loaded = True

        if self.backend == "vLLM":
            logger.info("vLLM 백엔드 - 로컬 모델 로드 불필요")
            return

        try:
            self._load_transformers()
            logger.info(f"LLM 모델 로드 완료: {self._get_model_name()}")
        except Exception as e:
            logger.warning(f"LLM 로드 실패 ({e}). Fallback mode.")
            self._model = None

    def _load_transformers(self) -> None:
        """Transformers 백엔드 로드"""
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_name = self.config["model_name"]
        device = self.config.get("device")
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        token = self.config.get("token")
        torch_dtype_str = self.config.get("torch_dtype", "float16")
        torch_dtype = torch.float16 if torch_dtype_str == "float16" else torch.float32

        # 디바이스가 CPU인 경우 float32 사용
        if device == "cpu":
            torch_dtype = torch.float32

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            token=token,
            trust_remote_code=True,
        )

        self._model = AutoModelForCausalLM.from_pretrained(
            model_name,
            token=token,
            trust_remote_code=True,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
            device_map="auto" if device == "cuda" else None,
        )

        if device == "cpu":
            self._model = self._model.to(device)

        self._model.eval()

        # 중국어 차단 processor 캐싱 (vocab 분석은 1회만 수행)
        self._chinese_processor = ChineseBlockingLogitsProcessor(self._tokenizer)

    def generate(self, prompt, **kargs):
        try:
            if self.backend == "vLLM":
                logger.info(f"vLLM에 의한 generate 시도")
                return self.generate_vLLM(prompt, **kargs)
            else:
                logger.info(f"local transformers에 의한 generate 시도")
                # transformers 백엔드는 npc_id를 사용하지 않으므로 제거
                kargs.pop("npc_id", None)
                return self.generate_transformers(prompt, **kargs)
        except Exception as e:
            logger.info(f"local transformers에 의한 generate 시도 : {e}")
            kargs.pop("npc_id", None)
            return self.generate_transformers(prompt, **kargs)

    def generate_vLLM(self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        repetition_penalty: float = DEFAULT_REPETITION_PENALTY,
        npc_id: str | None = None,
    ) -> str:
        """
        vLLM을 이용한 텍스트 생성 (통일된 인터페이스)

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (선택)
            max_tokens: 최대 토큰 수 (transformers: max_new_tokens)
            temperature: 샘플링 온도
            top_p: nucleus sampling
            repetition_penalty: 반복 패널티 (transformers만 사용)
            npc_id: NPC ID — vLLM 기동 시 --lora-modules로 등록된 어댑터 이름을 사용
                    등록된 어댑터가 없으면 base 모델로 생성

        Returns:
            생성된 텍스트
        """
        # NPC에 매핑된 어댑터 이름 조회 (vLLM --lora-modules로 사전 등록된 이름)
        adapter_name = get_adapter_model(npc_id)
        if adapter_name:
            model_to_use = adapter_name
            logger.info(f"LoRA 어댑터 사용: {adapter_name} (npc_id={npc_id})")
        else:
            model_to_use = self._model_name

        if system_prompt:
            formatted_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            formatted_prompt = prompt

        base = self.base_url.rstrip("/")
        resp = self._client.post(
            f"{base}/v1/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": model_to_use,
                "prompt": formatted_prompt,
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        logger.debug(f"vLLM resp status: {resp.status_code}")
        data = resp.json()
        logger.debug(f"vLLM resp data: {str(data)[:200]}")
        return data["choices"][0]["text"]

    def generate_transformers(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        repetition_penalty: float = DEFAULT_REPETITION_PENALTY,
    ) -> str:
        """
        텍스트 생성 (통일된 인터페이스)

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (선택)
            max_tokens: 최대 토큰 수 (transformers: max_new_tokens)
            temperature: 샘플링 온도
            top_p: nucleus sampling
            repetition_penalty: 반복 패널티 (transformers만 사용)

        Returns:
            생성된 텍스트
        """
        self._load_model()

        if self._model is None:
            logger.warning("LLM 사용 불가 (fallback: 빈 문자열)")
            return ""

        try:
            return self._generate_transformers(
                prompt, max_tokens, temperature, top_p, repetition_penalty
            )
        except Exception as e:
            logger.error(f"LLM 생성 실패: {e}", exc_info=True)
            return ""

    def _generate_transformers(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        repetition_penalty: float,
    ) -> str:
        """Transformers 백엔드로 생성"""
        import torch

        # 채팅 템플릿 사용 (모델이 지원하는 경우)
        if hasattr(self._tokenizer, "apply_chat_template"):
            messages = [{"role": "user", "content": prompt}]
            try:
                encoded = self._tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_dict=True,
                    return_tensors="pt",
                )
                input_ids = encoded["input_ids"].to(self._model.device)
                attention_mask = encoded["attention_mask"].to(self._model.device)
            except Exception:
                # apply_chat_template 실패 시 일반 토크나이징
                inputs = self._tokenizer(prompt, return_tensors="pt")
                input_ids = inputs["input_ids"].to(self._model.device)
                attention_mask = inputs.get("attention_mask", None)
                if attention_mask is not None:
                    attention_mask = attention_mask.to(self._model.device)
        else:
            # 일반 토크나이징
            inputs = self._tokenizer(prompt, return_tensors="pt")
            input_ids = inputs["input_ids"].to(self._model.device)
            attention_mask = inputs.get("attention_mask", None)
            if attention_mask is not None:
                attention_mask = attention_mask.to(self._model.device)

        # pad_token_id 설정
        pad_token_id = self._tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = self._tokenizer.eos_token_id

        # 생성
        from transformers import LogitsProcessorList
        chinese_processor = getattr(self, "_chinese_processor", None)
        logits_processor = LogitsProcessorList([chinese_processor]) if chinese_processor else None

        with torch.no_grad():
            outputs = self._model.generate(
                input_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_tokens,
                do_sample=True,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                eos_token_id=self._tokenizer.eos_token_id,
                pad_token_id=pad_token_id,
                logits_processor=logits_processor,
            )

        # 디코딩
        generated_tokens = outputs[0][input_ids.shape[-1]:]
        return self._tokenizer.decode(generated_tokens, skip_special_tokens=True).strip()

    def get_llm_with_tools(self, tools: list) -> Any:
        """
        Tool binding된 LLM 반환 (LangChain 전용)

        Args:
            tools: LangChain tool 리스트

        Returns:
            Tool이 바인딩된 LLM

        Raises:
            ValueError: transformers 백엔드에서 호출 시
        """
        if self.backend != "langchain":
            raise ValueError("get_llm_with_tools는 langchain 백엔드에서만 지원됩니다")

        self._load_model()
        if self._model is None:
            raise RuntimeError("LLM을 로드할 수 없습니다")

        return self._model.bind_tools(tools)

    @property
    def available(self) -> bool:
        """LLM 사용 가능 여부"""
        if self.backend == "vLLM":
            return True
        self._load_model()
        return self._model is not None

    @property
    def model_name(self) -> str:
        """현재 모델 이름"""
        return self._get_model_name()


# ============================================================
# 싱글턴 팩토리 함수들
# ============================================================

def get_llm(
    backend: str = DEFAULT_BACKEND,
    model_name: str | None = None,
) -> UnifiedLLMEngine:
    """
    싱글턴 LLM 엔진 인스턴스 반환

    Args:
        backend: "langchain" 또는 "transformers"
        model_name: 사용할 모델 (None이면 config 기본값)

    Returns:
        UnifiedLLMEngine 인스턴스
    """
    global _instance
    if _instance is None:
        _instance = UnifiedLLMEngine(backend=backend, model_name=model_name)
    return _instance


# 하위 호환성을 위한 별칭
LLM_Engine = UnifiedLLMEngine
LangChainEngine = UnifiedLLMEngine
GenerativeAgentsLLM = UnifiedLLMEngine

# 하위 호환성을 위한 팩토리 함수
def get_langchain_engine(
    model: str | None = None,
    base_url: str | None = None,
) -> UnifiedLLMEngine:
    """
    LangChain 엔진 반환 (하위 호환성)

    Args:
        model: 모델 이름
        base_url: API base URL

    Returns:
        UnifiedLLMEngine 인스턴스 (langchain 백엔드)
    """
    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url

    return get_llm(backend="langchain", model_name=model)

# 독립 실행 테스트
if __name__ == "__main__":
    from .config import NPC_ADAPTER_MAP

    logging.basicConfig(level=logging.INFO)

    llm_engine = UnifiedLLMEngine()
    # npc 프롬프트 리스트 (순서 기반)
    NPC_PROMPT_LIST = [
        {
            "id": "stepmother",
            "system_prompt": "당신은 집착이 강하고 통제적인 새엄마입니다. 공포 장르 톤을 유지하세요.",
        },
        {
            "id": "brother",
            "system_prompt": "당신은 외로움을 느끼는 동생입니다. 애정을 갈구하세요",
        },
        {
            "id": "dog_baron",
            "system_prompt": "월! 너가 할 수 있는 말의 전부입니다. 반복만 가능해요",
        },
    ]


    prompt = "플레이어가 당신에게 '여기서 나가고 싶어'라고 말했습니다. 대사 한마디를 하세요."

    print("=" * 60)
    print("LoRA 어댑터 전환 테스트")
    print(f"프롬프트: {prompt}")
    print("=" * 60)

    for i, npc in enumerate(NPC_PROMPT_LIST, 1):
        npc_id = npc["id"]
        system_prompt = npc["system_prompt"]
        adapter = NPC_ADAPTER_MAP.get(npc_id, "(base 모델)")
        print(f"\n[{i}] npc_id={npc_id} → {adapter}")
        print("-" * 40)
        resp = llm_engine.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            npc_id=npc_id,
        )
        print(f"응답: {resp}")

    # 새엄마(stepmother) 반복 대화 테스트 (10회)
    stepmother = NPC_PROMPT_LIST[0]
    print("\n" + "=" * 60)
    print(f"새엄마 반복 대화 테스트 (10회)")
    print(f"어댑터: {NPC_ADAPTER_MAP.get(stepmother['id'], '(base 모델)')}")
    print("=" * 60)

    conversation = []
    for turn in range(1, 11):
        user_input = input(f"\n[Turn {turn}/10] 플레이어 > ").strip()
        if not user_input or user_input == 'stop':
            break
        conversation.append(f"플레이어: {user_input}")

        prompt_with_history = (
            "대화 기록:\n" + "\n".join(conversation[-6:]) + "\n\n"
            f"플레이어가 '{user_input}'라고 말했습니다. 대사 한마디를 하세요."
        )

        resp = llm_engine.generate(
            prompt=prompt_with_history,
            system_prompt=stepmother["system_prompt"],
            npc_id=stepmother["id"],
        )
        print(f"새엄마 > {resp}")
        conversation.append(f"새엄마: {resp}")

    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)