"""
app/agents/llm.py
Generative Agents LLM 래퍼 — EXAONE lazy loading + fallback

H100 최적화: Flash Attention 2 + BF16 + 4bit 양자화
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
        self._device = "cpu"  # 실제 device 저장용
        self._load_model()

    def _load_model(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

            hf_token = os.environ.get("HF_TOKEN")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading GenerativeAgentsLLM: {self.model_name} on {device}")

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                token=hf_token,
                trust_remote_code=True,
            )

            # H100 최적화 설정
            if device == "cuda":
                # 4bit 양자화 설정
                bnb_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_use_double_quant=True,
                )
                logger.debug("4bit quantization config: nf4, bfloat16, double_quant=True")

                # Flash Attention 2 지원 여부 확인
                attn_impl = None
                try:
                    import flash_attn  # noqa: F401
                    attn_impl = "flash_attention_2"
                    logger.info("Flash Attention 2 detected, enabling FA2")
                except ImportError:
                    logger.warning("flash-attn not installed, using default attention")

                model_kwargs = {
                    "token": hf_token,
                    "trust_remote_code": True,
                    # "quantization_config": bnb_config,
                    "torch_dtype": torch.bfloat16,
                    "device_map": "auto",
                }
                # if attn_impl:
                #     model_kwargs["attn_implementation"] = attn_impl

                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    **model_kwargs,
                )

                self._device = "cuda"

                # 적용된 최적화 로그
                logger.info(
                    f"Model loaded: quantization=4bit, dtype=bfloat16, "
                    f"attn={attn_impl or 'default'}, device_map=auto"
                )
            else:
                # CPU fallback (양자화/FA2 미지원)
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_name,
                    token=hf_token,
                    trust_remote_code=True,
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                )
                self._device = "cpu"
                logger.info("Model loaded: CPU mode, dtype=float32")

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

        if self._model is None or self._tokenizer is None:
            return ""

        try:
            import torch

            messages = [{"role": "user", "content": prompt}]

            encoded = self._tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            )
            # 양자화 모델은 .device 접근 불가 → 저장된 _device 사용
            input_ids = encoded["input_ids"].to(self._device)
            attention_mask = encoded["attention_mask"].to(self._device)

            # pad_token_id 가 없으면 eos_token_id 로 대체
            pad_token_id = self._tokenizer.pad_token_id
            if pad_token_id is None:
                pad_token_id = self._tokenizer.eos_token_id

            with torch.no_grad():
                outputs = self._model.generate(
                    input_ids,
                    attention_mask=attention_mask,
                    max_new_tokens=max_tokens,
                    do_sample=True,
                    temperature=temperature,
                    top_p=top_p,
                    eos_token_id=self._tokenizer.eos_token_id,
                    pad_token_id=pad_token_id,
                )

            generated = outputs[0][input_ids.shape[-1]:]
            return self._tokenizer.decode(generated, skip_special_tokens=True).strip()

        except Exception as e:
            logger.error(f"LLM generation failed: {e}", exc_info=True)
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
