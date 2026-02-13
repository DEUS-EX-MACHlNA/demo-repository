"""
app/llm/config.py
LLM 모델 설정 관리
"""
import os
from typing import Literal

# 기본 모델 설정 (여기서 모델을 변경하세요)
DEFAULT_MODEL = "kakaocorp/kanana-1.5-8b-instruct-2505"
ALTERNATIVE_MODEL = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"

# LLM 백엔드 타입
LLMBackend = Literal["vLLM", "transformers"]
DEFAULT_BACKEND: LLMBackend = "vLLM"

# vLLM 설정
VLLM_BASE_URL = "https://nontheatrical-judiciarily-susanne.ngrok-free.dev/v1"

# Transformers 설정
TRANSFORMERS_DEVICE = None  # None이면 자동 감지 (cuda/cpu)
TRANSFORMERS_TORCH_DTYPE = "float16"  # cuda: float16, cpu: float32

# 생성 파라미터 기본값
DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_REPETITION_PENALTY = 1.1

# HuggingFace 토큰 (환경변수에서 로드)
HF_TOKEN = os.environ.get("HF_TOKEN")


def get_model_config(backend: LLMBackend | None = None) -> dict:
    """백엔드별 모델 설정 반환"""
    backend = backend or DEFAULT_BACKEND

    if backend == "vLLM":
        return {
            "model": DEFAULT_MODEL,
            "base_url": VLLM_BASE_URL,
            "temperature": DEFAULT_TEMPERATURE,
            "api_key": "EMPTY",
        }
    elif backend == "transformers":
        return {
            "model_name": DEFAULT_MODEL,
            "device": TRANSFORMERS_DEVICE,
            "torch_dtype": TRANSFORMERS_TORCH_DTYPE,
            "token": HF_TOKEN,
        }
    else:
        raise ValueError(f"Unknown backend: {backend}")
