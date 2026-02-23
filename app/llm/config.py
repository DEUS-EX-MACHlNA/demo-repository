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

# vLLM 설정 — .env의 VLLM_BASE_URL로 재정의 가능
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "https://46f9-34-118-241-224.ngrok-free.app/")
VLLM_SERVED_MODEL_NAME = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")

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

# NPC ID → vLLM LoRA 어댑터 등록 이름 매핑 (completions 요청 시 model 필드에 사용)
NPC_ADAPTER_MAP: dict[str, str] = {
    "stepmother": "stepmother_lora",
    "stepfather": "stepfather_lora",
    "brother": "brother_lora",
    "dog_baron": "dog_baron_lora",
    "grandmother": "grandmother_lora",
}

# NPC ID → HuggingFace LoRA 레포 경로 매핑
NPC_HF_REPO_MAP: dict[str, str] = {
    "stepmother":  "lucete171/deus-mother-lora",
    "stepfather":  "lucete171/deus-stepfather-lora",
    "brother":     "lucete171/deus-sibling-lora",
    "dog_baron":   "lucete171/deus-dog-baron-lora",
    "grandmother": "lucete171/deus-grandmother-lora",
}


def get_adapter_model(npc_id: str | None) -> str | None:
    """npc_id에 대응하는 vLLM LoRA 어댑터 등록 이름을 반환. 없으면 None."""
    if npc_id is None:
        return None
    return NPC_ADAPTER_MAP.get(npc_id)


def get_adapter_hf_repo(npc_id: str | None) -> str | None:
    """npc_id에 대응하는 HuggingFace 레포 경로를 반환. 없으면 None."""
    if npc_id is None:
        return None
    return NPC_HF_REPO_MAP.get(npc_id)


def get_model_config(backend: LLMBackend | None = None) -> dict:
    """백엔드별 모델 설정 반환"""
    backend = backend or DEFAULT_BACKEND

    if backend == "vLLM":
        return {
            "model": VLLM_SERVED_MODEL_NAME,
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

