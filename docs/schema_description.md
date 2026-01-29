# Pipeline Schema Description

전체 파이프라인의 각 단계별 입출력 스키마 정의

---

## 목차

- [API 엔드포인트](#api-엔드포인트)
- [1. Loader](#1-loader)
- [2. WorldStateManager.get_state](#2-worldstatemanagerget_state)
- [3. PromptParser](#3-promptparser)
- [4. ScenarioController](#4-scenariocontroller)
- [5. Execute Selected Tool](#5-execute-selected-tool)
- [6. tool_4: Night Comes](#6-tool_4-night-comes)
- [7. Delta Merge](#7-delta-merge)
- [8. WorldStateManager.apply_delta](#8-worldstatemanagerapply_delta)
- [9. Narrative Rendering](#9-narrative-rendering)
- [부록: 전체 스키마 정의](#부록-전체-스키마-정의)

---

## API 엔드포인트

### POST /v1/scenario/step

**Request Body:**

```json
{
  "user_id": "user_12345",
  "text": "피해자 가족에게 그날 무슨 일이 있었는지 물어본다"
}
```

| 필드        | 타입       | 필수 | 설명               |
| ----------- | ---------- | ---- | ------------------ |
| `user_id` | `string` | ✅   | 사용자 ID          |
| `text`    | `string` | ✅   | 사용자 입력 텍스트 |

**Response:**

```json
{
  "dialogue": "피해자 가족이 고개를 끄덕인다...\n\n---\n밤이 깊어간다...",
  "is_observed": false,
  "debug": {
    "user_id": "user_12345",
    "scenario_id": "culprit_ai",
    "steps": [...],
    "total_duration_ms": 125.5
  }
}
```

| 필드            | 타입        | 설명                    |
| --------------- | ----------- | ----------------------- |
| `dialogue`    | `string`  | 최종 사용자 출력 텍스트 |
| `is_observed` | `boolean` | 행동 관찰 여부          |
| `debug`       | `object`  | 디버그 정보 (선택적)    |

---

## 1. Loader

시나리오 YAML 파일들을 로드하여 ScenarioAssets 생성

### Input

시나리오 ID와 YAML 파일 경로들:

```
scenarios/
└── culprit_ai/
    ├── scenario.yaml
    ├── story_graph.yaml
    ├── npcs.yaml
    ├── items.yaml
    ├── memory_rules.yaml
    └── locks.yaml (선택)
```

**함수 시그니처:**

```python
load_scenario_assets(scenario_id: str) -> ScenarioAssets
```

### Output: ScenarioAssets

```json
{
  "scenario_id": "culprit_ai",
  "scenario": {
    "id": "culprit_ai",
    "title": "너는 이미 범인이다",
    "genre": "심리 스릴러 / 추리",
    "turn_limit": 12,
    "opening_scene_id": "act1_open",
    "state_schema": {
      "vars": {
        "clue_count": {"default": 0, "min": 0, "max": 10},
        "identity_match_score": {"default": 0, "min": 0, "max": 10},
        "fabrication_score": {"default": 0, "min": 0, "max": 10}
      },
      "flags": {
        "ending": {"default": null}
      }
    }
  },
  "npcs": {
    "npcs": [
      {
        "npc_id": "family",
        "name": "피해자 가족",
        "role": "증언자",
        "stats": {"trust": 0, "fear": 0, "suspicion": 0}
      }
    ]
  },
  "items": {
    "items": [
      {
        "item_id": "casefile_brief",
        "name": "사건 브리핑 팩",
        "type": "document",
        "acquire": {"method": "start"}
      }
    ]
  },
  "story_graph": {"nodes": [...]},
  "memory_rules": {"rewrite_rules": [...]}
}
```

---

## 2. WorldStateManager.get_state

현재 사용자/시나리오의 월드 상태 조회 (없으면 초기화)

### Input

```python
wsm.get_state(
    user_id="user_12345",
    scenario_id="culprit_ai",
    assets=scenario_assets  # 초기화 시 필요
)
```

| 파라미터        | 타입               | 필수 | 설명           |
| --------------- | ------------------ | ---- | -------------- |
| `user_id`     | `str`            | ✅   | 사용자 ID      |
| `scenario_id` | `str`            | ✅   | 시나리오 ID    |
| `assets`      | `ScenarioAssets` | ❌   | 초기화 시 필요 |

### Output: WorldState

```json
{
  "turn": 1,
  "npcs": {
    "family": {
      "npc_id": "family",
      "trust": 0,
      "fear": 0,
      "suspicion": 0,
      "extras": {}
    },
    "partner": {
      "npc_id": "partner",
      "trust": 0,
      "fear": 0,
      "suspicion": 1,
      "extras": {}
    },
    "witness": {
      "npc_id": "witness",
      "trust": 0,
      "fear": 2,
      "suspicion": 0,
      "extras": {}
    }
  },
  "flags": {
    "ending": null
  },
  "inventory": [
    "casefile_brief",
    "pattern_analyzer",
    "memo_pad"
  ],
  "locks": {},
  "vars": {
    "clue_count": 0,
    "identity_match_score": 0,
    "fabrication_score": 0
  }
}
```

**WorldState 필드:**

| 필드          | 타입       | 설명                             |
| ------------- | ---------- | -------------------------------- |
| `turn`      | `int`    | 현재 턴 (1~)                     |
| `npcs`      | `object` | NPC 상태 맵 (npc_id → NPCState) |
| `flags`     | `object` | 게임 플래그 (ending, act 등)     |
| `inventory` | `array`  | 소유 아이템 ID 목록              |
| `locks`     | `object` | 잠금/해금 상태                   |
| `vars`      | `object` | 시나리오 변수                    |

---

## 3. PromptParser

사용자 입력을 분석하여 의도와 대상 추출

### Input

```python
parser.parse(
    text="그러니까 범인은 현장에 있었던 거 맞지?",
    assets=scenario_assets,
    world_snapshot=world_before
)
```

| 파라미터           | 타입               | 설명               |
| ------------------ | ------------------ | ------------------ |
| `text`           | `str`            | 사용자 입력 텍스트 |
| `assets`         | `ScenarioAssets` | 시나리오 에셋      |
| `world_snapshot` | `WorldState`     | 현재 월드 상태     |

### Output: ParsedInput

```json
{
  "intent": "leading",
  "target": "family",
  "content": "그러니까 범인은 현장에 있었던 거 맞지?",
  "raw": "그러니까 범인은 현장에 있었던 거 맞지?"
}
```

| 필드        | 타입           | 설명                                                                             |
| ----------- | -------------- | -------------------------------------------------------------------------------- |
| `intent`  | `str`        | 감지된 의도 (`leading`, `neutral`, `empathic`, `summarize`, `unknown`) |
| `target`  | `str \| null` | 대상 (NPC ID 또는 item ID)                                                       |
| `content` | `str`        | 정제된 내용                                                                      |
| `raw`     | `str`        | 원본 텍스트                                                                      |

**Intent 타입:**

| Intent        | 설명      | 예시              |
| ------------- | --------- | ----------------- |
| `leading`   | 유도 질문 | "그러니까 ~맞지?" |
| `neutral`   | 중립 질문 | "언제 사건이?"    |
| `empathic`  | 공감 표현 | "힘드셨겠네요"    |
| `summarize` | 요약/정리 | "정리하면 ~이다"  |
| `unknown`   | 불명확    | -                 |

---

## 4. ScenarioController

ParsedInput 분석하여 실행할 Tool 결정

### Input

```python
controller.decide(
    parsed=parsed_input,
    world_snapshot=world_before,
    assets=scenario_assets
)
```

| 파라미터           | 타입               | 설명           |
| ------------------ | ------------------ | -------------- |
| `parsed`         | `ParsedInput`    | 파싱된 입력    |
| `world_snapshot` | `WorldState`     | 현재 월드 상태 |
| `assets`         | `ScenarioAssets` | 시나리오 에셋  |

### Output: ToolCall

```json
{
  "tool_name": "npc_talk",
  "args": {
    "npc_id": "family",
    "intent": "leading",
    "content": "그러니까 범인은 현장에 있었던 거 맞지?"
  }
}
```

| 필드          | 타입       | 설명                                                   |
| ------------- | ---------- | ------------------------------------------------------ |
| `tool_name` | `str`    | 실행할 Tool (`npc_talk`, `action`, `item_usage`) |
| `args`      | `object` | Tool별 인자                                            |

**Tool별 args:**

**npc_talk:**

```json
{
  "npc_id": "family",
  "intent": "leading",
  "content": "질문 내용"
}
```

**action:**

```json
{
  "action_type": "summarize",  // summarize | investigate | move | observe
  "target": null,
  "content": "행동 내용"
}
```

**item_usage:**

```json
{
  "item_id": "pattern_analyzer",
  "action_id": "analyze_self",
  "target": null
}
```

---

## 5. Execute Selected Tool

선택된 Tool 실행 (tool_1/2/3 중 택 1)

### Input

```python
execute_tool(
    tool_name="npc_talk",
    args={"npc_id": "family", "intent": "leading", ...},
    world_snapshot=world_before,
    assets=scenario_assets
)
```

| 파라미터           | 타입               | 설명          |
| ------------------ | ------------------ | ------------- |
| `tool_name`      | `str`            | Tool 이름     |
| `args`           | `dict`           | Tool 인자     |
| `world_snapshot` | `WorldState`     | 현재 상태     |
| `assets`         | `ScenarioAssets` | 시나리오 에셋 |

### Output: ToolResult

```json
{
  "state_delta": {
    "npc_stats": {
      "family": {
        "trust": -1
      }
    },
    "vars": {
      "fabrication_score": 1
    }
  },
  "event_description": "피해자 가족이(가) 잠시 망설이다가 고개를 끄덕인다. \"...그렇게 생각하신다면요.\""
}
```

| 필드              | 타입       | 설명                 |
| ----------------- | ---------- | -------------------- |
| `state_delta`   | `object` | 상태 변경 델타       |
| `text_fragment` | `str`    | 내러티브 텍스트 조각 |

---

## 6. tool_4: Night Comes

매 턴 종료 시 항상 1회 실행 (턴 증가, NPC 변화, 관찰 판정)

### Input

```python
tool_4_night_comes(
    world_snapshot=world_before,
    assets=scenario_assets
)
```

| 파라미터           | 타입               | 설명          |
| ------------------ | ------------------ | ------------- |
| `world_snapshot` | `WorldState`     | 현재 상태     |
| `assets`         | `ScenarioAssets` | 시나리오 에셋 |

### Output: NightResult

```json
{
  "night_delta": {
    "turn_increment": 1,
    "npc_stats": {
      "family": {
        "suspicion": 1,
        "trust": -1
      },
      "partner": {
        "suspicion": 1
      }
    },
    "vars": {}
  },
  "night_dialogue": "밤이 깊어간다. 진실과 조작의 경계가 흐려진다.\n\n...누군가 당신의 로그를 확인했다.",
  "is_observed": true
}
```

| 필드               | 타입       | 설명                                 |
| ------------------ | ---------- | ------------------------------------ |
| `night_delta`    | `object` | 밤 시간대 상태 변경                  |
| `night_dialogue` | `str`    | 밤 내러티브                          |
| `is_observed`    | `bool`   | 관찰 여부 (fabrication_score에 비례) |

---

## 7. Delta Merge

tool 실행 델타 + night 델타 병합

### Input

```python
merged_delta = merge_deltas(
    tool_result.state_delta,
    night_result.night_delta
)
```

| 파라미터    | 타입     | 설명          |
| ----------- | -------- | ------------- |
| `*deltas` | `dict` | 병합할 델타들 |

### Output: StateDelta (merged)

```json
{
  "npc_stats": {
    "family": {
      "trust": -2,
      "suspicion": 1
    }
  },
  "flags": {},
  "inventory_add": [],
  "inventory_remove": [],
  "locks": {},
  "vars": {
    "fabrication_score": 1
  },
  "turn_increment": 1
}
```

**StateDelta 필드:**

| 필드                 | 타입       | 설명          | 병합 규칙                    |
| -------------------- | ---------- | ------------- | ---------------------------- |
| `npc_stats`        | `object` | NPC 스탯 변경 | 숫자 합산                    |
| `flags`            | `object` | 플래그 변경   | 덮어쓰기                     |
| `inventory_add`    | `array`  | 추가 아이템   | 배열 병합                    |
| `inventory_remove` | `array`  | 제거 아이템   | 배열 병합                    |
| `locks`            | `object` | 잠금 변경     | 덮어쓰기                     |
| `vars`             | `object` | 변수 변경     | 숫자면 합산, 아니면 덮어쓰기 |
| `turn_increment`   | `int`    | 턴 증가       | 숫자 합산                    |

---

## 8. WorldStateManager.apply_delta

병합된 델타를 월드 상태에 적용

### Input

```python
world_after = wsm.apply_delta(
    user_id="user_12345",
    scenario_id="culprit_ai",
    delta=merged_delta,
    assets=scenario_assets
)
```

| 파라미터        | 타입               | 설명                        |
| --------------- | ------------------ | --------------------------- |
| `user_id`     | `str`            | 사용자 ID                   |
| `scenario_id` | `str`            | 시나리오 ID                 |
| `delta`       | `dict`           | 적용할 델타                 |
| `assets`      | `ScenarioAssets` | 시나리오 에셋 (범위 검증용) |

### Output: WorldState (updated)

```json
{
  "turn": 2,
  "npcs": {
    "family": {
      "npc_id": "family",
      "trust": 0,
      "fear": 0,
      "suspicion": 1,
      "extras": {}
    }
  },
  "flags": {"ending": null},
  "inventory": ["casefile_brief", "pattern_analyzer", "memo_pad"],
  "locks": {},
  "vars": {
    "clue_count": 0,
    "identity_match_score": 0,
    "fabrication_score": 1
  }
}
```

**적용 규칙:**

- **NPC 스탯**: 델타 더하기 → 0~100 클램프
- **Vars**: 숫자면 델타 더하기 + min/max 클램프, 아니면 덮어쓰기
- **Flags/Locks**: 덮어쓰기
- **Inventory**: add/remove 리스트로 추가/제거
- **Turn**: turn_increment만큼 증가

---

## 9. Narrative Rendering

최종 사용자 출력 텍스트 조립

### Input

```python
dialogue = narrative.render(
    text_fragment="피해자 가족이 고개를 끄덕인다...",
    night_dialogue="밤이 깊어간다...",
    world_before=world_before,
    world_after=world_after,
    assets=scenario_assets
)
```

| 파라미터           | 타입               | 설명                  |
| ------------------ | ------------------ | --------------------- |
| `text_fragment`  | `str`            | Tool 실행 결과 텍스트 |
| `night_dialogue` | `str`            | 밤 내러티브           |
| `world_before`   | `WorldState`     | 액션 전 상태          |
| `world_after`    | `WorldState`     | 액션 후 상태          |
| `assets`         | `ScenarioAssets` | 시나리오 에셋         |

### Output: dialogue (string)

```
피해자 가족이(가) 잠시 망설이다가 고개를 끄덕인다. "...그렇게 생각하신다면요."
세계가 당신의 관점에 맞춰 조정되었다.

---
밤이 깊어간다. 진실과 조작의 경계가 흐려진다.

[턴 2/12]
```

**렌더링 구조:**

1. `text_fragment` (Tool 결과)
2. 상태 변화 묘사 (선택적)
3. `---` 구분선
4. `night_dialogue`
5. 턴 정보 `[턴 X/Y]`
6. 엔딩 메시지 (조건 충족 시)

---

## 부록: 전체 스키마 정의

### TypeScript 타입 정의

```typescript
// ==================== WorldState ====================
interface WorldState {
  turn: number;
  npcs: Record<string, NPCState>;
  flags: Record<string, any>;
  inventory: string[];
  locks: Record<string, boolean>;
  vars: Record<string, any>;
}

interface NPCState {
  npc_id: string;
  trust: number;    // 0~100
  fear: number;     // 0~100
  suspicion: number; // 0~100
  extras: Record<string, any>;
}

// ==================== Parser ====================
type Intent = "leading" | "neutral" | "empathic" | "summarize" | "unknown";

interface ParsedInput {
  intent: Intent;
  target: string | null;
  content: string;
  raw: string;
}

// ==================== Controller ====================
type ToolName = "npc_talk" | "action" | "item_usage";

interface ToolCall {
  tool_name: ToolName;
  args: Record<string, any>;
}

// ==================== Tools ====================
interface ToolResult {
  state_delta: StateDelta;
  text_fragment: string;
}

interface NightResult {
  night_delta: StateDelta;
  night_dialogue: string;
  is_observed: boolean;
}

// ==================== State Delta ====================
interface StateDelta {
  npc_stats: Record<string, Record<string, number>>;
  flags: Record<string, any>;
  inventory_add: string[];
  inventory_remove: string[];
  locks: Record<string, boolean>;
  vars: Record<string, any>;
  turn_increment: number;
}

// ==================== API ====================
interface StepRequest {
  user_id: string;
  text: string;
}

interface StepResponse {
  dialogue: string;
  is_observed: boolean;
  debug?: Record<string, any>;
}
```

### JSON Schema (OpenAPI)

```yaml
WorldState:
  type: object
  required: [turn, npcs, flags, inventory, locks, vars]
  properties:
    turn:
      type: integer
      minimum: 1
    npcs:
      type: object
      additionalProperties:
        $ref: '#/components/schemas/NPCState'
    flags:
      type: object
      additionalProperties: true
    inventory:
      type: array
      items:
        type: string
    locks:
      type: object
      additionalProperties:
        type: boolean
    vars:
      type: object
      additionalProperties: true

NPCState:
  type: object
  required: [npc_id, trust, fear, suspicion]
  properties:
    npc_id:
      type: string
    trust:
      type: integer
      minimum: 0
      maximum: 100
    fear:
      type: integer
      minimum: 0
      maximum: 100
    suspicion:
      type: integer
      minimum: 0
      maximum: 100
    extras:
      type: object
```

### 전체 데이터 흐름 예시

```
Request
  → {user_id: "user_12345", text: "그러니까 범인은 현장에 있었던 거 맞지?"}

1. Loader
  → ScenarioAssets {scenario_id: "culprit_ai", ...}

2. get_state
  → WorldState {turn: 1, npcs: {...}, vars: {clue_count: 0, ...}}

3. parse
  → ParsedInput {intent: "leading", target: "family", ...}

4. decide
  → ToolCall {tool_name: "npc_talk", args: {...}}

5. execute_tool
  → ToolResult {state_delta: {npc_stats: {family: {trust: -1}}, vars: {fabrication_score: 1}}, text_fragment: "..."}

6. night_comes
  → NightResult {night_delta: {turn_increment: 1, ...}, night_dialogue: "...", is_observed: false}

7. merge_deltas
  → StateDelta {npc_stats: {...}, vars: {...}, turn_increment: 1}

8. apply_delta
  → WorldState {turn: 2, npcs: {...}, vars: {fabrication_score: 1, ...}}

9. render
  → dialogue: "피해자 가족이 고개를 끄덕인다...\n\n---\n밤이 깊어간다...\n\n[턴 2/12]"

Response
  → {dialogue: "...", is_observed: false, debug: {...}}
```
