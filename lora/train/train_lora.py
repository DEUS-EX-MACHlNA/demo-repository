"""
LoRA Training Script for EXAONE 7.8B Monster Style
==================================================
Google Colab 환경에서 실행

목적: 몬스터 말투(문장 구조, 반복, 붕괴된 문법, 의성어/의태어, 광기 표현)만 학습
주의: 게임 로직, humanity 변수, 상태 전이, semantic role은 포함하지 않음

사용법:
    !python train_lora.py --config config.yaml
"""

import os
import yaml
import argparse
import torch
from pathlib import Path
from typing import Dict, Any
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import (
    LoraConfig,
    get_peft_model,
    prepare_model_for_kbit_training,
    TaskType,
)
from trl import SFTTrainer


def load_config(config_path: str) -> Dict[str, Any]:
    """설정 파일 로드"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_quantization(config: Dict[str, Any]) -> BitsAndBytesConfig:
    """양자화 설정"""
    quant_config = config.get("quantization", {})

    return BitsAndBytesConfig(
        load_in_4bit=quant_config.get("load_in_4bit", True),
        bnb_4bit_compute_dtype=getattr(
            torch, quant_config.get("bnb_4bit_compute_dtype", "bfloat16")
        ),
        bnb_4bit_quant_type=quant_config.get("bnb_4bit_quant_type", "nf4"),
        bnb_4bit_use_double_quant=quant_config.get("bnb_4bit_use_double_quant", True),
    )


def setup_lora(config: Dict[str, Any]) -> LoraConfig:
    """LoRA 설정"""
    lora_config = config.get("lora", {})

    return LoraConfig(
        r=lora_config.get("r", 16),
        lora_alpha=lora_config.get("lora_alpha", 32),
        lora_dropout=lora_config.get("lora_dropout", 0.05),
        target_modules=lora_config.get("target_modules", [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj"
        ]),
        bias=lora_config.get("bias", "none"),
        task_type=TaskType.CAUSAL_LM,
    )


def load_model_and_tokenizer(config: Dict[str, Any], bnb_config: BitsAndBytesConfig):
    """모델과 토크나이저 로드"""
    model_config = config.get("model", {})
    model_name = model_config.get("name", "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct")

    print(f"Loading model: {model_name}")

    # 토크나이저 로드
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=model_config.get("trust_remote_code", True),
    )

    # 패딩 토큰 설정
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # 모델 로드 (4bit 양자화)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map=model_config.get("device_map", "auto"),
        trust_remote_code=model_config.get("trust_remote_code", True),
        torch_dtype=getattr(torch, model_config.get("torch_dtype", "bfloat16")),
    )

    # Gradient checkpointing을 위한 준비
    model = prepare_model_for_kbit_training(model)

    return model, tokenizer


def load_training_data(config: Dict[str, Any]):
    """학습 데이터 로드"""
    data_config = config.get("data", {})
    train_file = data_config.get("train_file", "../data/monster_style.jsonl")

    # JSONL 파일 로드
    dataset = load_dataset("json", data_files=train_file, split="train")

    print(f"Loaded {len(dataset)} training samples")
    return dataset


def format_instruction(sample: Dict[str, str]) -> str:
    """
    학습 데이터를 EXAONE instruction format으로 변환

    EXAONE format:
    [|system|]시스템 메시지[|endofturn|]
    [|user|]사용자 입력[|endofturn|]
    [|assistant|]어시스턴트 응답[|endofturn|]
    """
    system_msg = "당신은 몬스터입니다. 붕괴된 문법, 반복, 의성어를 사용하여 말하세요."

    if sample.get("input"):
        user_msg = f"{sample['instruction']}\n\n{sample['input']}"
    else:
        user_msg = sample["instruction"]

    formatted = (
        f"[|system|]{system_msg}[|endofturn|]\n"
        f"[|user|]{user_msg}[|endofturn|]\n"
        f"[|assistant|]{sample['output']}[|endofturn|]"
    )

    return formatted


def setup_training_args(config: Dict[str, Any]) -> TrainingArguments:
    """학습 인자 설정"""
    train_config = config.get("training", {})

    return TrainingArguments(
        output_dir=train_config.get("output_dir", "../adapters/exaone-7.8b-monster-lora"),
        num_train_epochs=train_config.get("num_train_epochs", 3),
        per_device_train_batch_size=train_config.get("per_device_train_batch_size", 2),
        gradient_accumulation_steps=train_config.get("gradient_accumulation_steps", 8),
        learning_rate=train_config.get("learning_rate", 2e-4),
        weight_decay=train_config.get("weight_decay", 0.01),
        warmup_ratio=train_config.get("warmup_ratio", 0.03),
        lr_scheduler_type=train_config.get("lr_scheduler_type", "cosine"),
        logging_steps=train_config.get("logging_steps", 10),
        save_steps=train_config.get("save_steps", 100),
        save_total_limit=train_config.get("save_total_limit", 3),
        fp16=train_config.get("fp16", False),
        bf16=train_config.get("bf16", True),
        max_grad_norm=train_config.get("max_grad_norm", 0.3),
        optim=train_config.get("optim", "paged_adamw_32bit"),
        gradient_checkpointing=train_config.get("gradient_checkpointing", True),
        group_by_length=train_config.get("group_by_length", True),
        report_to=train_config.get("report_to", "none"),
        remove_unused_columns=False,
    )


def train(config_path: str):
    """메인 학습 함수"""
    print("=" * 60)
    print("Monster Style LoRA Training for EXAONE 7.8B")
    print("=" * 60)
    print("\n목적: 몬스터 말투(문장 구조, 반복, 붕괴된 문법, 의성어/의태어, 광기 표현)만 학습")
    print("주의: 게임 로직, humanity 변수, 상태 전이, semantic role은 포함하지 않음\n")

    # 설정 로드
    config = load_config(config_path)
    print(f"Config loaded from: {config_path}")

    # 양자화 설정
    bnb_config = setup_quantization(config)
    print("Quantization config ready (4-bit NF4)")

    # LoRA 설정
    lora_config = setup_lora(config)
    print(f"LoRA config ready (r={lora_config.r}, alpha={lora_config.lora_alpha})")

    # 모델 & 토크나이저 로드
    model, tokenizer = load_model_and_tokenizer(config, bnb_config)
    print("Model and tokenizer loaded")

    # LoRA 적용
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 학습 데이터 로드
    dataset = load_training_data(config)

    # 학습 인자 설정
    training_args = setup_training_args(config)

    # SFTTrainer 설정
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        formatting_func=format_instruction,
        max_seq_length=config.get("data", {}).get("max_seq_length", 512),
    )

    # 학습 시작
    print("\n" + "=" * 60)
    print("Starting training...")
    print("=" * 60 + "\n")

    trainer.train()

    # 모델 저장
    output_dir = config.get("training", {}).get(
        "output_dir", "../adapters/exaone-7.8b-monster-lora"
    )
    print(f"\nSaving model to: {output_dir}")

    # LoRA 어댑터만 저장
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    print("\n" + "=" * 60)
    print("Training completed!")
    print("=" * 60)


def test_inference(adapter_path: str, prompt: str = "안녕하세요"):
    """학습된 LoRA로 추론 테스트"""
    from peft import PeftModel

    config_path = "config.yaml"
    config = load_config(config_path)
    model_config = config.get("model", {})
    model_name = model_config.get("name", "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct")

    # 기본 모델 로드
    bnb_config = setup_quantization(config)
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    # LoRA 어댑터 로드
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    # 프롬프트 포맷
    system_msg = "당신은 몬스터입니다. 붕괴된 문법, 반복, 의성어를 사용하여 말하세요."
    formatted_prompt = (
        f"[|system|]{system_msg}[|endofturn|]\n"
        f"[|user|]{prompt}[|endofturn|]\n"
        f"[|assistant|]"
    )

    inputs = tokenizer(formatted_prompt, return_tensors="pt").to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=128,
            temperature=0.8,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.pad_token_id,
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=False)
    # assistant 응답만 추출
    response = response.split("[|assistant|]")[-1].replace("[|endofturn|]", "").strip()

    print(f"Input: {prompt}")
    print(f"Monster Response: {response}")

    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train LoRA for Monster Style")
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run inference test instead of training"
    )
    parser.add_argument(
        "--adapter_path",
        type=str,
        default="../adapters/exaone-7.8b-monster-lora",
        help="Path to adapter for testing"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="안녕하세요, 만나서 반갑습니다.",
        help="Test prompt"
    )

    args = parser.parse_args()

    if args.test:
        test_inference(args.adapter_path, args.prompt)
    else:
        train(args.config)
