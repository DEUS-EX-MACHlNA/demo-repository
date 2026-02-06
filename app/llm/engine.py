"""
app/llm/engine.py
통합 LLM 엔진 - LangChain 및 Transformers 백엔드 지원
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .config import (
    DEFAULT_BACKEND,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_REPETITION_PENALTY,
    get_model_config,
)

logger = logging.getLogger(__name__)

_instance: Optional[UnifiedLLMEngine] = None


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
            backend: "langchain" 또는 "transformers"
            model_name: 사용할 모델 (None이면 config에서 로드)
            **kwargs: 백엔드별 추가 설정
        """
        self.backend = backend
        self._model = None
        self._loaded = False

        # 설정 로드
        self.config = get_model_config(backend)
        if model_name:
            if backend == "langchain":
                self.config["model"] = model_name
            else:
                self.config["model_name"] = model_name

        # 추가 설정 병합
        self.config.update(kwargs)

        logger.info(f"UnifiedLLMEngine 초기화: backend={backend}, model={self._get_model_name()}")

    def _get_model_name(self) -> str:
        """현재 모델 이름 반환"""
        if self.backend == "langchain":
            return self.config.get("model", "unknown")
        else:
            return self.config.get("model_name", "unknown")

    def _load_model(self) -> None:
        """모델 로드 (lazy loading)"""
        if self._loaded:
            return
        self._loaded = True

        try:
            if self.backend == "langchain":
                self._load_langchain()
            elif self.backend == "transformers":
                self._load_transformers()
            else:
                raise ValueError(f"Unknown backend: {self.backend}")

            logger.info(f"LLM 모델 로드 완료: {self._get_model_name()}")
        except Exception as e:
            logger.warning(f"LLM 로드 실패 ({e}). Fallback mode.")
            self._model = None

    def _load_langchain(self) -> None:
        """LangChain 백엔드 로드"""
        from langchain_openai import ChatOpenAI

        self._model = ChatOpenAI(
            model=self.config["model"],
            base_url=self.config["base_url"],
            api_key=self.config["api_key"],
            temperature=self.config.get("temperature", DEFAULT_TEMPERATURE),
        )

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

    def generate(
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
            if self.backend == "langchain":
                return self._generate_langchain(
                    prompt, system_prompt, max_tokens, temperature
                )
            elif self.backend == "transformers":
                return self._generate_transformers(
                    prompt, max_tokens, temperature, top_p, repetition_penalty
                )
            else:
                return ""
        except Exception as e:
            logger.error(f"LLM 생성 실패: {e}", exc_info=True)
            return ""

    def _generate_langchain(
        self,
        prompt: str,
        system_prompt: str | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """LangChain 백엔드로 생성"""
        from langchain_core.messages import HumanMessage, SystemMessage

        print(f"[LLM] 모델: {self._get_model_name()}")
        logger.info(f"generate 호출 - 모델: {self._get_model_name()}")

        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        response = self._model.invoke(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        print(f"[LLM] 응답 수신 완료 (길이: {len(response.content)}자)")
        return response.content

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
