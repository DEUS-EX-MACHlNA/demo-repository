"""
Monster Style Data Generator for LoRA Training
===============================================
목적: 몬스터 말투 학습용 데이터 생성
- 말투, 문장 구조, 반복, 붕괴된 문법, 의성어/의태어, 광기 표현
- 게임 로직, humanity 변수, 상태 전이, semantic role은 포함하지 않음

Google Colab 환경에서 실행
"""

import json
import random
from pathlib import Path
from typing import List, Dict


# 몬스터 말투 변환 패턴
class MonsterStylePatterns:
    """몬스터 말투 패턴 정의"""

    # 의성어/의태어
    ONOMATOPOEIA = [
        "크르르...", "끼이익...", "으르렁...", "히히힉...", "캬하하...",
        "쉬이익...", "그르르릉...", "꺄악...", "키키킥...", "흐흐흑...",
        "푸하하...", "크큭...", "끄으윽...", "쿠쿠쿡...", "카카칵..."
    ]

    # 광기 표현
    MADNESS_EXPRESSIONS = [
        "피...피가 필요해...", "어둠이...보여...", "그것이...부른다...",
        "살...살점이...", "눈알이...굴러간다...", "뼈가...부서지는 소리...",
        "내장이...꿈틀대...", "영혼이...울부짖어...", "고통이...달콤해...",
        "죽음의...냄새가...", "피비린내가...좋아...", "고기...고기가 필요해..."
    ]

    # 반복 패턴
    REPETITION_PATTERNS = [
        ("죽", "죽...죽여...죽여버려..."),
        ("먹", "먹...먹어...먹어치워..."),
        ("아프", "아파...아파아파아파..."),
        ("배고프", "배고파...배고파배고파..."),
        ("춥", "추워...추워추워추워..."),
        ("무섭", "무서워...무서워무서워..."),
        ("싫", "싫어...싫어싫어싫어...")
    ]

    # 붕괴된 문법 패턴
    BROKEN_GRAMMAR = [
        ("입니다", "...다..."),
        ("합니다", "...해..."),
        ("습니다", "...어..."),
        ("세요", "...라..."),
        ("하세요", "...해...해..."),
        ("주세요", "...줘...줘..."),
        ("입니까", "...야...?"),
        ("할게요", "...할...거...야..."),
        ("할 수 있어요", "...할 수...있...어..."),
        ("하겠습니다", "...하...겠...어...")
    ]

    # 문장 종결 변형
    SENTENCE_ENDINGS = [
        "...", "...!", "...?", "...흐흐...", "...크크...",
        "...으으...", "...아아...", "...히히...", "...끼익..."
    ]


def apply_repetition(text: str) -> str:
    """단어 반복 패턴 적용"""
    for keyword, replacement in MonsterStylePatterns.REPETITION_PATTERNS:
        if keyword in text:
            if random.random() < 0.7:
                text = text.replace(keyword, replacement.split("...")[0] + "...")
    return text


def apply_broken_grammar(text: str) -> str:
    """붕괴된 문법 적용"""
    for formal, broken in MonsterStylePatterns.BROKEN_GRAMMAR:
        if formal in text:
            text = text.replace(formal, broken)
    return text


def add_onomatopoeia(text: str) -> str:
    """의성어/의태어 추가"""
    if random.random() < 0.5:
        ono = random.choice(MonsterStylePatterns.ONOMATOPOEIA)
        position = random.choice(["prefix", "suffix", "both"])
        if position == "prefix":
            text = f"{ono} {text}"
        elif position == "suffix":
            text = f"{text} {ono}"
        else:
            ono2 = random.choice(MonsterStylePatterns.ONOMATOPOEIA)
            text = f"{ono} {text} {ono2}"
    return text


def add_madness(text: str) -> str:
    """광기 표현 추가"""
    if random.random() < 0.3:
        madness = random.choice(MonsterStylePatterns.MADNESS_EXPRESSIONS)
        text = f"{text} {madness}"
    return text


def fragment_sentence(text: str) -> str:
    """문장을 파편화"""
    words = text.split()
    if len(words) > 3 and random.random() < 0.4:
        # 랜덤하게 말줄임표 삽입
        insert_pos = random.randint(1, len(words) - 1)
        words.insert(insert_pos, "...")
    return " ".join(words)


def modify_ending(text: str) -> str:
    """문장 종결 변형"""
    # 기존 마침표/종결 제거
    text = text.rstrip(".")
    text = text.rstrip("!")
    text = text.rstrip("?")
    # 새로운 종결 추가
    ending = random.choice(MonsterStylePatterns.SENTENCE_ENDINGS)
    return text + ending


def transform_to_monster_style(normal_text: str) -> str:
    """일반 텍스트를 몬스터 말투로 변환"""
    text = normal_text

    # 1. 붕괴된 문법 적용
    text = apply_broken_grammar(text)

    # 2. 반복 패턴 적용
    text = apply_repetition(text)

    # 3. 문장 파편화
    text = fragment_sentence(text)

    # 4. 의성어/의태어 추가
    text = add_onomatopoeia(text)

    # 5. 광기 표현 추가
    text = add_madness(text)

    # 6. 문장 종결 변형
    text = modify_ending(text)

    return text


# 샘플 정상 문장 (학습 데이터 기반)
NORMAL_SENTENCES = [
    "안녕하세요, 만나서 반갑습니다.",
    "오늘 날씨가 좋네요.",
    "배가 고파요, 뭔가 먹고 싶어요.",
    "여기가 어디인가요?",
    "도와주세요.",
    "무섭습니다.",
    "아프지 않게 해주세요.",
    "나는 여기서 기다리겠습니다.",
    "당신은 누구입니까?",
    "이곳은 위험합니다.",
    "빨리 도망가세요.",
    "저를 따라오세요.",
    "조심하세요, 적이 옵니다.",
    "물이 필요합니다.",
    "춥습니다, 불이 필요해요.",
    "혼자 있고 싶습니다.",
    "왜 이러는 거예요?",
    "살려주세요.",
    "제발 그만하세요.",
    "더 이상 못 참겠어요.",
    "어둠이 무섭습니다.",
    "소리가 들립니다.",
    "뭔가 다가오고 있어요.",
    "숨을 곳이 필요해요.",
    "함께 가시겠습니까?",
    "이것은 무엇입니까?",
    "시간이 없습니다.",
    "기다려주세요.",
    "잠시만요.",
    "알겠습니다."
]


def generate_training_data(
    num_samples: int = 500,
    output_path: str = "../data/monster_style.jsonl"
) -> None:
    """
    몬스터 말투 학습 데이터 생성

    Args:
        num_samples: 생성할 샘플 수
        output_path: 출력 파일 경로
    """
    data = []

    for i in range(num_samples):
        # 랜덤하게 정상 문장 선택
        normal = random.choice(NORMAL_SENTENCES)

        # 몬스터 말투로 변환
        monster = transform_to_monster_style(normal)

        # 학습 데이터 포맷 (instruction-following 형식)
        sample = {
            "instruction": "다음 문장을 몬스터처럼 말해줘.",
            "input": normal,
            "output": monster
        }
        data.append(sample)

    # 순수 몬스터 발화 추가 (instruction 없이)
    for i in range(num_samples // 2):
        monster_utterance = generate_pure_monster_utterance()
        sample = {
            "instruction": "몬스터처럼 말해줘.",
            "input": "",
            "output": monster_utterance
        }
        data.append(sample)

    # 저장
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Generated {len(data)} samples -> {output_path}")


def generate_pure_monster_utterance() -> str:
    """순수 몬스터 발화 생성"""
    templates = [
        "크르르... {onomatopoeia} 배고파...배고파배고파... {madness}",
        "{onomatopoeia} 왜...왜 이래... 아파...아파아파... {ending}",
        "누구...누구야... {onomatopoeia} 무서워...무서워무서워... {madness}",
        "{onomatopoeia} 피...피가... 빨간...빨간 것이... {ending}",
        "어둠...어둠이... {onomatopoeia} 보여...보여보여... {madness}",
        "살...살점이... {onomatopoeia} 필요해...필요해... {ending}",
        "{onomatopoeia} 여기...여기는... 춥...춥다... {madness}",
        "누가...누가 불러... {onomatopoeia} 들려...들려... {ending}",
        "{madness} {onomatopoeia} 오고 있어...오고 있어... {ending}",
        "먹...먹어야... {onomatopoeia} 살...살아야... {madness}"
    ]

    template = random.choice(templates)

    return template.format(
        onomatopoeia=random.choice(MonsterStylePatterns.ONOMATOPOEIA),
        madness=random.choice(MonsterStylePatterns.MADNESS_EXPRESSIONS),
        ending=random.choice(MonsterStylePatterns.SENTENCE_ENDINGS)
    )


def create_chat_format_data(
    input_path: str = "../data/monster_style.jsonl",
    output_path: str = "../data/monster_style_chat.jsonl"
) -> None:
    """
    EXAONE chat format으로 변환
    """
    data = []

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)

            # EXAONE chat format
            if item["input"]:
                user_content = f"{item['instruction']}\n\n{item['input']}"
            else:
                user_content = item["instruction"]

            chat_item = {
                "messages": [
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": item["output"]}
                ]
            }
            data.append(chat_item)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Converted to chat format -> {output_path}")


if __name__ == "__main__":
    # 기본 데이터 생성
    generate_training_data(num_samples=500)

    # Chat format 변환
    create_chat_format_data()

    # 샘플 출력
    print("\n=== Sample Monster Utterances ===")
    for _ in range(5):
        normal = random.choice(NORMAL_SENTENCES)
        monster = transform_to_monster_style(normal)
        print(f"Normal: {normal}")
        print(f"Monster: {monster}")
        print("-" * 50)
