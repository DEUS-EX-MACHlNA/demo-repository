"""
app/agents/llm.py
Generative Agents LLM 래퍼 — EXAONE lazy loading + fallback

narrative.py / parser.py 와 동일한 패턴을 따른다.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_instance: Optional[GenerativeAgentsLLM] = None


class GenerativeAgentsLLM:
    """EXAONE 기반 텍스트 생성. 모델 없으면 빈 문자열 반환(fallback)."""

    def __init__(self, model_name: str = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"):
        self.model_name = model_name
        self._model = None
        self._tokenizer = None
        self._loaded = False

    # ── lazy load ────────────────────────────────────────────
    def _load_model(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            hf_token = os.environ.get("HF_TOKEN")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading GenerativeAgentsLLM: {self.model_name} on {device}")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                token=hf_token,
                trust_remote_code=True,
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                token=hf_token,
                trust_remote_code=True,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
                device_map="auto" if device == "cuda" else "cpu",
            )
            logger.info("GenerativeAgentsLLM loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load LLM ({e}). Falling back to rule-based.")
            self._model = None
            self._tokenizer = None

    # ── 생성 ─────────────────────────────────────────────────
    def generate(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """프롬프트로부터 텍스트 생성. 모델 없으면 빈 문자열."""
        self._load_model()
        if self._model is None or self._tokenizer is None:
            return ""

        try:
            import torch

            messages = [{"role": "user", "content": prompt}]
            input_ids = self._tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            ).to(self._model.device)

            with torch.no_grad():
                outputs = self._model.generate(
                    input_ids,
                    max_new_tokens=max_tokens,
                    do_sample=True,
                    temperature=temperature,
                    top_p=top_p,
                    eos_token_id=self._tokenizer.eos_token_id,
                    pad_token_id=self._tokenizer.pad_token_id,
                )

            generated = outputs[0][input_ids.shape[1]:]
            return self._tokenizer.decode(generated, skip_special_tokens=True).strip()

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return ""

    @property
    def available(self) -> bool:
        self._load_model()
        return self._model is not None


def get_llm() -> GenerativeAgentsLLM:
    """싱글턴 LLM 인스턴스."""
    global _instance
    if _instance is None:
        _instance = GenerativeAgentsLLM()
    return _instance
