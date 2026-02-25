# 백엔드 응답 형식 구체화 문서

## 개요

자연어 처리 기반 world state 판단을 백엔드에 맡기는 경우의 구체적인 응답 형식입니다.

---

## 1. 전체 응답 구조

```json
{
  "narrative": "string",           // 필수: 게임 내 표시할 대화/서술 텍스트
  "ending_info": {                 // 선택적: 엔딩 트리거 정보
    "ending_id": "string",          // 엔딩 ID (null이면 엔딩 없음)
    "name": "string",               // 엔딩 이름
    "epilogue_prompt": "string"     // 엔딩 에필로그 프롬프트 (선택적)
  },
  "state_result": {                // 필수: 상태 결과값 (Result 형식)
    "npc_stats": {...},            // 선택적: NPC 통계 현재 값
    "npc_disabled_states": {...},  // 선택적: NPC 무력화 상태
    "inventory_add": [...],         // 선택적: 아이템 획득
    "inventory_remove": [...],     // 선택적: 아이템 소모
    "flags": {...},                 // 선택적: 시나리오/엔딩 분기용 플래그
    "humanity": 0.0                 // 선택적: 플레이어 인간성 현재 값
  },
  "debug": {                       // 선택적: 디버그 정보
    "game_id": 24,
    "reasoning": "string",          // 백엔드 판단 근거
    "steps": [...],
    "turn_after": 0
  }
}
```

---

## 2. 각 필드 상세 설명

### 2.1 narrative (필수)

- **타입**: `string`
- **설명**: 플레이어에게 표시할 대화/서술 텍스트
- **예시**: `"새엄마가 말했습니다. '참 착한 아이구나'"`

### 2.2 ending_info (선택적)

- **타입**: `object` 또는 `null`
- **설명**: 엔딩 조건 충족 시 트리거 정보

```json
{
  "ending_id": "stealth_exit", // 엔딩 ID (null이면 엔딩 없음)
  "name": "완벽한 기만 (Stealth Exit)", // 엔딩 이름
  "epilogue_prompt": "가족들을 수면제로 잠재우고 유유히 탈출했다." // 엔딩 에필로그 프롬프트 (선택적)
}
```

**엔딩 ID 값:**

- `"stealth_exit"`, → `EndingType.StealthExit`
- `"chaotic_breakout"` → `EndingType.ChaoticBreakout`
- `"siblings_help"` → `EndingType.SiblingsHelp`
- `"unfinished_doll"` → `EndingType.UnfinishedDoll`
- `"eternal_dinner"` → `EndingType.EternalDinner`
- `null` 또는 `"none"` → 엔딩 없음

### 2.3 state_result (필수)

상태 결과값을 Result 형식으로 전달합니다. 백엔드에서 델타 값을 처리한 최종 상태를 반환합니다. **변경되지 않은 필드는 생략 가능**합니다.

#### 2.3.1 npc_stats (선택적)

NPC 통계 현재 값 (호감도, 의심도, 공포도)

```json
{
  "npc_stats": {
    "new_mother": {
      "trust": 50.0, // 호감도 현재 값 (0~100)
      "suspicion": 10.0, // 의심도 현재 값 (현재 미사용)
      "fear": 0.0 // 공포도 현재 값 (현재 미사용)
    },
    "grandmother": {
      "trust": 60.0,
      "suspicion": 0.0,
      "fear": 0.0
    }
  }
}
```

**NPC 이름 매핑:**

- `"new_mother"`, `"stepmother"` → `NPCType.NewMother`
- `"new_father"`, `"father"` → `NPCType.NewFather`
- `"sibling"`, `"brother"` → `NPCType.Sibling`
- `"dog"`, `"baron"` → `NPCType.Dog`
- `"grandmother"` → `NPCType.Grandmother`

**주의사항:**

- 변경되지 않은 NPC는 생략 가능
- 새엄마는 `humanity` 변경 불가 (최종보스)

#### 2.3.3 inventory_add (선택적)

획득한 아이템 목록

```json
{
  "inventory_add": [
    "sleeping_pill", // 아이템 이름 (개수는 기본값 1)
    "earl_grey_tea"
  ]
}
```

**아이템 이름 매핑:**

- `"sleeping_pill"` → `ItemType.SleepingPill`
- `"earl_grey_tea"` → `ItemType.EarlGreyTea`
- `"real_family_photo"` → `ItemType.RealFamilyPhoto`
- `"oil_bottle"` → `ItemType.OilBottle`
- `"silver_lighter"` → `ItemType.SilverLighter`
- `"siblings_toy"` → `ItemType.SiblingsToy`
- `"brass_key"` → `ItemType.BrassKey`
- `"livingroom_photo"` → `ItemType.LivingroomPhoto`
- `"hole"` → `ItemType.Hole`

**주의사항:**

- 빈 배열이면 생략 가능
- 개수는 기본값 1 (필요 시 확장 가능)

#### 2.3.4 inventory_remove (선택적)

소모/사용한 아이템 목록

```json
{
  "inventory_remove": ["sleeping_pill"]
}
```

**주의사항:**

- 빈 배열이면 생략 가능

#### 2.3.5 npc_disabled_states (선택적)

NPC 무력화 상태 (수면제 등으로 무력화)

```json
{
  "npc_disabled_states": {
    "grandmother": {
      "is_disabled": true,
      "remaining_turns": 3,
      "reason": "수면제 복용"
    },
    "new_father": {
      "is_disabled": true,
      "remaining_turns": 2,
      "reason": "수면제 복용"
    },
    "new_mother": {
      "is_disabled": true,
      "remaining_turns": 1,
      "reason": "수면제 복용"
    }
  }
}
```

**주의사항:**

- `is_disabled: false`이면 생략 가능 (무력화 해제)
- `remaining_turns: 0`이면 무력화 해제

#### 2.3.6 flags (선택적)

시나리오·엔딩 분기용 플래그. 프론트는 플래그 값에 따라 특정 동작(예: NPC 무력화, 다음 Day NPC 비활성화, 밤 대화 분기)을 수행한다.

```json
{
  "flags": {
    "tea_with_sleeping_pill": true,
    "sibling_escape_plan_agreed": true
  }
}
```

**플래그 예시 (엔딩/시나리오별):**

- `tea_with_sleeping_pill`: `true` — 홍차에 수면제 투여됨. 프론트는 새 Day 시작 시 가족 전원 3턴 무력화 후 플래그를 false로 되돌림. (완벽한 기만)
- `sibling_escape_plan_agreed`: `true` — 액자 보여 준 뒤 설정. 다음 Day에 새엄마·새아빠·동생 비활성화용. (조력자의 희생)

**주의사항:**

- 변경되지 않은 플래그는 생략 가능
- 각 엔딩/시나리오 문서(예: `완벽한기만.md`, `조력자의 희생.md`)에서 필수 플래그 및 의미 참조

#### 2.3.7 humanity (선택적)

플레이어 인간성 현재 값

```json
{
  "humanity": 75.0 // 플레이어 인간성 현재 값 (0~100)
}
```

**주의사항:**

- 변경되지 않았으면 생략 가능
- 0~100 범위의 값

### 2.4 debug (선택적)

디버그 정보

```json
{
  "debug": {
    "game_id": 24,
    "reasoning": "수면제 복용",
    "steps": [],
    "turn_after": 6
  }
}
```

**필드 설명:**

- `reasoning`: 백엔드가 판단한 근거 (디버깅용)
- `steps`: 시나리오 스텝 정보 (선택적)
- `turn_after`: 처리 후 턴 수 (선택적)

---

## 3. 실제 사용 예시

### 예시 1: 변화 없음 (단순 대화)

**요청:**

```json
{
  "chat_input": "안녕하세요",
  "npc_name": "stepfather",
  "item_name": ""
}
```

**응답:**

```json
{
  "narrative": "새아빠가 무표정하게 당신을 바라봅니다.",
  "ending_info": null,
  "state_result": {
    "npc_stats": {
      "new_father": {
        "trust": 51.0
      }
    }
  }
}
```

### 주요 엔딩 시나리오

- **완벽한 기만** — 엔딩에 이르는 단계별 조건·요청/응답 예시·테스트 데이터는 **`마크다운/백엔드/완벽한기만.md`** 를 참조할 것.

---

## 4. Night 대화 응답

**엔드포인트:** `POST /api/v1/game/{gameId}/night_dialogue`  
(요청 Body는 없거나 빈 객체 `{}`. 턴이 0이 되었을 때 프론트가 자동 호출.)

일반 스텝 응답 구조를 그대로 사용하되, **최상위에 `dialogues` 배열**을 추가한 형태입니다. 프론트는 이 배열을 순서대로 화면에 표시합니다.

### 4.1 전체 응답 구조

```json
{
  "narrative": "string 또는 생략",
  "dialogues": [
    {
      "speaker_name": "string",
      "dialogue": "string"
    }
  ],
  "ending_info": { ... },
  "state_result": { ... },
  "debug": { ... }
}
```

- **`narrative`**: 선택적. Night 대화 응답에서는 생략 가능. 있으면 서술/요약용으로 사용할 수 있음.
- **`dialogues`**: **Night 전용.** 대화 라인 배열. 순서대로 표시됨.
- **`ending_info`**, **`state_result`**, **`debug`**: 일반 스텝 응답과 동일(생략 가능).

### 4.2 dialogues 상세

| 필드           | 타입   | 설명                                                          |
| -------------- | ------ | ------------------------------------------------------------- |
| `speaker_name` | string | 화자 표시 이름 (예: `"엘리노어 (새엄마)"`, `"루카스 (동생)"`) |
| `dialogue`     | string | 해당 화자의 대사 한 줄                                        |

**주의사항:**

- `dialogues`가 비어 있거나 `null`이면 프론트는 “밤의 대화 없음”으로 처리(예: 가족 전원 수면제로 무력화된 경우).
- 배열 순서 = 재생/표시 순서.

### 4.3 사용 예시

#### 예시 A: 가족이 깨어 있을 때 (일반 밤 대화)

**응답:**

```json
{
  "narrative": "저녁 식사 후 가족이 거실에 모여 수다를 나눕니다.",
  "dialogues": [
    {
      "speaker_name": "엘리노어 (새엄마)",
      "dialogue": "오늘 우리 아이가 보여준 미소 보셨나요? 드디어 이 집의 향기에 적응한 것 같아 마음이 놓여요."
    },
    {
      "speaker_name": "아더 (새아빠)",
      "dialogue": "음, 확실히 소란을 피우지 않더군. 낮 동안 방 안에서 얌전히 지내는 걸 확인했소."
    },
    {
      "speaker_name": "루카스 (동생)",
      "dialogue": "오늘 누나가 나랑 같이 인형 집으로 한참 놀아줬어. 이제 우리 진짜 가족이 된 거지, 엄마?"
    }
  ],
  "ending_info": null,
  "state_result": {
    "humanity": 90,
    "npc_stats": {
      "new_mother": { "trust": 75, "suspicion": 0, "fear": 0 },
      "new_father": { "trust": 50, "suspicion": 0, "fear": 0 },
      "sibling": { "trust": 50, "suspicion": 0, "fear": 0 }
    }
  },
  "debug": {
    "game_id": 24,
    "reasoning": "밤의 대화: 가족이 거실에서 대화를 나눔.",
    "turn_after": 0
  }
}
```

#### 예시 B: 가족 수면제로 수면 중 (대화 없음)

**응답:** (`Assets/TestData/Scenarios/night_dialogue_family_asleep.json` 참고)

```json
{
  "dialogues": [
    { "speaker_name": "엘리노어 (새엄마)", "dialogue": "..." },
    { "speaker_name": "아더 (새아빠)", "dialogue": "..." },
    { "speaker_name": "루카스 (동생)", "dialogue": "..." }
  ],
  "ending_info": null,
  "state_result": {
    "humanity": 90,
    "npc_stats": {
      "new_mother": { "trust": 75, "suspicion": 0, "fear": 0 },
      "new_father": { "trust": 50, "suspicion": 0, "fear": 0 },
      "sibling": { "trust": 50, "suspicion": 0, "fear": 0 }
    },
    "flags": { "family_asleep": true, "tea_with_sleeping_pill": true },
    "npc_disabled_states": {
      "new_mother": {
        "is_disabled": true,
        "remaining_turns": -1,
        "reason": "sleeping_pill"
      },
      "new_father": {
        "is_disabled": true,
        "remaining_turns": -1,
        "reason": "sleeping_pill"
      },
      "sibling": {
        "is_disabled": true,
        "remaining_turns": -1,
        "reason": "sleeping_pill"
      }
    }
  },
  "debug": {
    "game_id": 24,
    "reasoning": "플레이어가 홍차에 수면제를 투여하여 가족들이 모두 잠들었습니다. 밤의 대화가 발생하지 않습니다.",
    "turn_after": 0
  }
}
```

- `dialogues`는 빈 배열 `[]`로 보내거나, placeholder(예: `"..."`)로 채워 보내도 됨. 프론트는 `family_asleep` 등 `state_result`를 적용해 가족 무력화를 반영함.
