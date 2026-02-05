# Monster Style Training Data

## 목적

이 데이터셋은 **몬스터 말투**만을 학습하기 위한 용도입니다.

### 학습 대상
- 말투 (speech patterns)
- 문장 구조 (sentence structure)
- 반복 (repetition)
- 붕괴된 문법 (broken grammar)
- 의성어/의태어 (onomatopoeia)
- 광기 표현 (madness expressions)

### 학습 제외 대상
- ❌ 게임 로직
- ❌ humanity 변수
- ❌ 상태 전이 (state transition)
- ❌ semantic role

## 데이터 형식

### JSONL 포맷
```json
{
  "instruction": "다음 문장을 몬스터처럼 말해줘.",
  "input": "안녕하세요, 만나서 반갑습니다.",
  "output": "크르르... 안...안녕... 만나...만나서... 으르렁... 반가...워..."
}
```

### 데이터 유형

1. **변환형**: 정상 문장 → 몬스터 말투 변환
   - instruction: "다음 문장을 몬스터처럼 말해줘."
   - input: 정상 문장
   - output: 몬스터 말투로 변환된 문장

2. **생성형**: 순수 몬스터 발화
   - instruction: "몬스터처럼 말해줘."
   - input: "" (빈 문자열)
   - output: 몬스터 스타일 발화

## 몬스터 말투 패턴

### 의성어/의태어
```
크르르..., 끼이익..., 으르렁..., 히히힉..., 캬하하...
쉬이익..., 그르르릉..., 꺄악..., 키키킥..., 흐흐흑...
```

### 반복 패턴
```
죽...죽여...죽여버려...
먹...먹어...먹어치워...
아파...아파아파아파...
배고파...배고파배고파...
```

### 붕괴된 문법
```
"입니다" → "...다..."
"합니다" → "...해..."
"세요" → "...라..."
"할게요" → "...할...거...야..."
```

### 광기 표현
```
피...피가 필요해...
어둠이...보여...
그것이...부른다...
눈알이...굴러간다...
고통이...달콤해...
```

## 데이터 생성

`generate_data.py`를 실행하여 추가 데이터를 생성할 수 있습니다:

```bash
cd ../train
python generate_data.py
```

기본적으로 500개의 변환형 샘플과 250개의 생성형 샘플이 생성됩니다.

## 파일 목록

| 파일명 | 설명 |
|--------|------|
| `monster_style.jsonl` | 기본 학습 데이터 |
| `monster_style_chat.jsonl` | Chat format 변환 데이터 (generate_data.py 실행 시 생성) |

## Google Colab 사용법

```python
# 데이터 로드
from datasets import load_dataset

dataset = load_dataset("json", data_files="monster_style.jsonl", split="train")
print(f"Total samples: {len(dataset)}")
```
