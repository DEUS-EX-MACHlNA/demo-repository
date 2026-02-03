"""
app/llm/langchain_engine.py
LangChain ChatOpenAI + HuggingFace Router 기반 LLM 엔진
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_instance: Optional["LangChainEngine"] = None


class LangChainEngine:
    """LangChain ChatOpenAI + HuggingFace Router 기반 LLM 엔진"""

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        base_url: str = "https://router.huggingface.co/v1",
        temperature: float = 0.7,
    ):
        from langchain_openai import ChatOpenAI

        self.model = model
        self.base_url = base_url
        self.temperature = temperature

        api_key = os.environ.get("HF_TOKEN")
        if not api_key:
            logger.warning("HF_TOKEN 환경변수가 설정되지 않았습니다.")

        self.llm = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
        )
        logger.info(f"LangChainEngine 초기화: model={model}, base_url={base_url}")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 512,
        temperature: float | None = None,
    ) -> str:
        """단순 텍스트 생성 (기존 LLM_Engine 호환)"""
        from langchain_core.messages import HumanMessage, SystemMessage

        messages: list[Any] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        try:
            response = self.llm.invoke(
                messages,
                max_tokens=max_tokens,
                temperature=temperature or self.temperature,
            )
            return response.content
        except Exception as e:
            logger.error(f"LLM 생성 실패: {e}")
            return ""

    def get_llm_with_tools(self, tools: list) -> Any:
        """Tool binding된 LLM 반환"""
        return self.llm.bind_tools(tools)

    @property
    def available(self) -> bool:
        """LLM 사용 가능 여부"""
        return self.llm is not None


def get_langchain_engine(
    model: str = "Qwen/Qwen2.5-7B-Instruct",
    base_url: str = "https://router.huggingface.co/v1",
) -> LangChainEngine:
    """싱글턴 LangChainEngine 인스턴스"""
    global _instance
    if _instance is None:
        _instance = LangChainEngine(model=model, base_url=base_url)
    return _instance
