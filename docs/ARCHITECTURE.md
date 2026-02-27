# DeusExMachina 아키텍처

## 레이어별 클래스 다이어그램

### 1. 스키마 레이어 (Schemas)

```
┌─────────────────────────────────────────────────────────────┐
│                      SCHEMAS LAYER                          │
└─────────────────────────────────────────────────────────────┘

WorldState (메인 런타임 상태)
├── turn: int
├── npcs: Dict[str, NPCState]
│   └── NPCState
│       ├── npc_id: str
│       ├── stats: Dict[str, int]      ← 동적 스탯 (affection, fear, humanity 등)
│       └── memory: Dict[str, Any]     ← LLM 기억 (memory_stream, current_plan 등)
├── flags: Dict[str, Any]
├── inventory: List[str]
├── locks: Dict[str, bool]
├── vars: Dict[str, Any]               ← 월드 변수 (humanity, suspicion_level 등)
└── active_events: List[str]

StateDelta (상태 변경 명세)
├── npc_stats: Dict[str, Dict[str, int]]   ← {npc_id: {stat_name: delta}}
├── flags: Dict[str, Any]
├── inventory_add/remove: List[str]
├── locks: Dict[str, bool]
├── vars: Dict[str, Any]
├── turn_increment: int
├── memory_updates: Dict[str, Any]
└── next_node: Optional[str]
```

---

### 2. 로더/에셋 레이어 (Loader & Assets)

```
┌─────────────────────────────────────────────────────────────┐
│              LOADER & ASSETS LAYER                          │
└─────────────────────────────────────────────────────────────┘

ScenarioLoader
└── load(scenario_id: str) → ScenarioAssets

ScenarioAssets
├── scenario_id: str
├── scenario: Dict[str, Any]           ← scenario.yaml 전체
│   ├── title, genre, tone, pov
│   ├── turn_limit
│   ├── state_schema
│   │   ├── vars: {var_name: {default, min, max}}
│   │   ├── flags: {flag_name: {default}}
│   │   └── system: {turn: {default}}
│   └── endings: List[EndingSchema]
├── story_graph: Dict[str, Any]        ← story_graph.yaml
├── npcs: Dict[str, Any]               ← npcs.yaml
│   └── npcs: List[NpcSchema]
│       ├── npc_id: str
│       ├── name: str
│       ├── stats: Dict[str, int]      ← 초기 스탯 (YAML에서 정의)
│       ├── persona: Dict[str, Any]
│       └── memory: Dict[str, Any]
├── items: Dict[str, Any]              ← items.yaml
├── memory_rules: Dict[str, Any]       ← memory_rules.yaml
│   └── rewrite_rules: List[RuleSchema]
│       ├── rule_id: str
│       ├── when: str (intent 조건)
│       └── effects: List[EffectSchema]
└── extras: Dict[str, Any]             ← locks.yaml 등

Methods:
├── get_npc_by_id(npc_id) → Dict
├── get_item_by_id(item_id) → Dict
├── get_all_npc_ids() → List[str]
├── get_all_item_ids() → List[str]
├── get_npc_stat_names() → List[str]   ← 🆕 동적 스탯 이름 추출
├── get_turn_limit() → int
├── get_state_schema() → Dict
└── export_for_prompt() → List[str]
```

---

### 3. 낮 파이프라인 (Day Pipeline)

```
┌──────────────────────────────────────────────────────────────┐
│               DAY PIPELINE LAYER                             │
└──────────────────────────────────────────────────────────────┘

DayController
├── process(
│   user_input: str,
│   world_state: WorldState,
│   assets: ScenarioAssets
│ ) → ToolResult
└── decision_log: List[Dict]

  ┌─────────────────────────────────────┐
  │  1. Tool Calling (tools.call_tool)  │
  ├─────────────────────────────────────┤
  │ Input: user_input, world_state      │
  │ LLM: 어떤 tool을 사용할지 선택     │
  │ Output: {tool_name, args, intent}   │
  └─────────────────────────────────────┘
           ↓
  ┌─────────────────────────────────────┐
  │  2. Tool Execution (tools.TOOLS)    │
  ├─────────────────────────────────────┤
  │ interact(target, interact)          │
  │ action(action)                      │
  │ use(item, action)                   │
  │                                     │
  │ Each calls LLM with:                │
  │ - build_talk/action/item_prompt()   │
  │   (+ assets 파라미터 추가됨)       │
  │                                     │
  │ Returns: {                          │
  │   event_description: List[str],     │
  │   state_delta: Dict                 │
  │ }                                   │
  └─────────────────────────────────────┘
           ↓
  ┌─────────────────────────────────────┐
  │  3. Final Value → Delta              │
  │  (_final_values_to_delta)            │
  ├─────────────────────────────────────┤
  │ LLM 최종값을 delta(변화량)으로     │
  │ 변환 (stats Dict 기반)             │
  └─────────────────────────────────────┘
           ↓
  ┌─────────────────────────────────────┐
  │  4. Rule Engine (rule_engine)       │
  ├─────────────────────────────────────┤
  │ apply_memory_rules(intent)          │
  │ → memory_rules 적용                 │
  │ → rule_delta 생성                   │
  └─────────────────────────────────────┘
           ↓
  ┌─────────────────────────────────────┐
  │  5. Delta Merge                     │
  │  (merge_rule_delta)                 │
  ├─────────────────────────────────────┤
  │ tool_delta + rule_delta 병합       │
  │ → 최종 state_delta                  │
  └─────────────────────────────────────┘
           ↓
    ToolResult(
      event_description: List[str],
      state_delta: Dict
    )
```

---

### 4. 밤 파이프라인 (Night Pipeline)

```
┌──────────────────────────────────────────────────────────────┐
│               NIGHT PIPELINE LAYER                           │
└──────────────────────────────────────────────────────────────┘

NightController
├── process(
│   world_snapshot: WorldState,
│   assets: ScenarioAssets
│ ) → NightResult
└── llm: GenerativeAgentsLLM

NightResult
├── night_delta: Dict[str, Any]
└── night_conversation: List[Dict]

  ┌──────────────────────────────────────┐
  │  Phase 1: Reflection                 │
  │  (_run_reflections)                  │
  ├──────────────────────────────────────┤
  │ For each NPC:                        │
  │ ├─ should_reflect() 체크             │
  │ └─ perform_reflection()              │
  │    → memory stream에 insights 저장   │
  └──────────────────────────────────────┘
           ↓
  ┌──────────────────────────────────────┐
  │  Phase 2: Planning                   │
  │  (_run_planning)                     │
  ├──────────────────────────────────────┤
  │ For each NPC:                        │
  │ └─ update_plan(                      │
  │      npc_id, name, persona,          │
  │      npc_memory, stats (Dict),       │ ← 🆕 동적 스탯
  │      turn, turn_limit, scenario      │
  │    )                                 │
  │    ├─ generate_long_term_plan()     │
  │    ├─ generate_short_term_plan()    │
  │    │  (emotion_str = format_emotion) │
  │    └─ save to memory                 │
  └──────────────────────────────────────┘
           ↓
  ┌──────────────────────────────────────┐
  │  Phase 3: Group Dialogue             │
  │  (_run_dialogues)                    │
  ├──────────────────────────────────────┤
  │ For NUM_GROUP_UTTERANCES iterations: │
  │ ├─ speaker_id = random.choice(npc)  │
  │ ├─ _generate_utterance(              │
  │ │    speaker_id, name, persona,      │
  │ │    memory, stats (Dict),           │ ← 🆕 동적 스탯
  │ │    listener, conversation, llm     │
  │ │  )                                 │
  │ └─ conversation 리스트에 추가        │
  │                                      │
  │ store_dialogue_memories():           │
  │ └─ 대화를 모든 NPC memory에 저장    │
  └──────────────────────────────────────┘
           ↓
  ┌──────────────────────────────────────┐
  │  Phase 4: Impact Analysis            │
  │  (_analyze_impacts)                  │
  ├──────────────────────────────────────┤
  │ For each NPC pair:                   │
  │ └─ analyze_conversation_impact(      │
  │      npc1_id, name, persona,         │
  │      npc2_id, name, persona,         │
  │      conversation, llm,              │
  │      stat_names (List[str])          │ ← 🆕 동적 스탯 이름
  │    )                                 │
  │    └─ parse_stat_changes_text()      │
  │       (stat_names 기반 파싱)        │
  │                                      │
  │ night_delta["npc_stats"] 누적      │
  └──────────────────────────────────────┘
           ↓
    NightResult(
      night_delta,
      night_conversation
    )
```

---

### 5. LLM & 프롬프트 레이어

```
┌──────────────────────────────────────────────────────────────┐
│              LLM & PROMPT LAYER                              │
└──────────────────────────────────────────────────────────────┘

build_output_format(stat_names: List[str] | None) → str
├── 동적으로 OUTPUT_FORMAT 생성
├── stat_names가 있으면 스탯 예시 포함
└── LLM 프롬프트에 "사용 가능한 스탯: ..." 명시

build_talk_prompt(message, ..., assets) → str
├── SYSTEM_PROMPT_TALK
├── 세계 상태, 기억, 등장인물 정보
└── build_output_format(assets.get_npc_stat_names())

build_action_prompt(action, ..., assets) → str
├── SYSTEM_PROMPT_ACTION
├── 세계 상태, 행동 정보
└── build_output_format(assets.get_npc_stat_names())

build_item_prompt(item_name, ..., assets) → str
├── SYSTEM_PROMPT_ITEM
├── 아이템 정보
└── build_output_format(assets.get_npc_stat_names())

parse_response(raw_text: str) → LLM_Response
├── _extract_json()
├── state_delta: Dict (LLM이 반환한 최종값)
└── event_description: List[str]

Agents Module
├── utils.py
│   ├── format_emotion(stats: Dict[str, int]) → str  ← 🆕 동적 스탯
│   ├── parse_stat_changes_text(text, stat_names) → Dict  ← 🆕 동적 파싱
│   └── extract_number, clamp
├── dialogue.py
│   ├── _generate_utterance(..., speaker_stats, ...) → str  ← 🆕 동적 스탯
│   ├── generate_dialogue(..., npc1_stats, npc2_stats, ...) → List
│   ├── analyze_conversation_impact(..., stat_names) → Dict  ← 🆕 동적 스탯
│   └── store_dialogue_memories(...)
└── planning.py
    ├── generate_long_term_plan(...) → str
    ├── generate_short_term_plan(..., stats, ...) → str  ← 🆕 동적 스탯
    └── update_plan(..., stats, ...) → str  ← 🆕 동적 스탯
```

---

### 6. 상태 관리 레이어

```
┌──────────────────────────────────────────────────────────────┐
│            STATE MANAGEMENT LAYER                            │
└──────────────────────────────────────────────────────────────┘

WorldStateManager
├── get_state(user_id, scenario_id, assets) → WorldState
├── apply_delta(user_id, scenario_id, delta, assets) → WorldState
├── persist(user_id, scenario_id, state)
├── reset_state(user_id, scenario_id)
└── [내부] 파일/DB 기반 영속화

LockManager
├── check_unlocks(world_state, locks_data) → LockResult
└── unlock_info(world_state, info_id) → bool

EndingChecker
├── check_ending(world_state, assets) → EndingCheckResult
└── evaluate_condition(condition_str) → bool
```

---

### 7. 나레이션/렌더링 레이어

```
┌──────────────────────────────────────────────────────────────┐
│           NARRATIVE RENDERING LAYER                          │
└──────────────────────────────────────────────────────────────┘

NarrativeLayer
├── render_day(
│   event_description,
│   state_delta,
│   world_state,
│   assets
│ ) → str (낮 나레이션)
│
├── render_night(
│   world_state,
│   assets,
│   night_conversation
│ ) → str (밤 나레이션)
│
├── render_ending(
│   ending_info,
│   world_state,
│   assets
│ ) → str (엔딩 나레이션)
│
└── [내부 메서드]
    ├── _collect_narrative_changes()
    │  └─ state_delta를 자연어로 변환 (동적 스탯)
    ├── _render_npc_state_summary()
    │  └─ NPC 상태 요약 (동적 스탯)
    ├── _collect_night_summary()
    └── _render_ending_narrative()
```

---

### 8. API/메인 레이어

```
┌──────────────────────────────────────────────────────────────┐
│              MAIN API LAYER (FastAPI)                        │
└──────────────────────────────────────────────────────────────┘

main.py (FastAPI app)
├── execute_day_pipeline(user_id, scenario_id, user_text)
│  └─ 낮 파이프라인 통합
├── execute_night_pipeline(user_id, scenario_id)
│  └─ 밤 파이프라인 통합
├── POST /v1/scenario/{id}/day
├── POST /v1/scenario/{id}/night
├── GET /v1/scenario/view/{id}
├── GET /v1/scenario/{id}/state/{user_id}
├── DELETE /v1/scenario/{id}/state/{user_id}
└── GET /health

game_loop.py (로컬 테스트용)
├── GameLoop(scenario_id)
├── day_turn(user_input) → Dict
├── night_phase() → NightResult
├── check_ending() → Dict | None
└── [내부] _apply_state_delta, _evaluate_condition
```

---

## 데이터 흐름 (Day Turn)

```
User Input
    ↓
DayController.process()
    ├─ call_tool()
    │  ├─ LLM: build_tool_prompt() (assets 사용)
    │  └─ parse_tool_response() → {tool_name, args, intent}
    │
    ├─ TOOLS[tool_name]() (interact, action, use)
    │  ├─ build_talk/action/item_prompt(assets)  ← 동적 스탯 포함
    │  ├─ LLM generate
    │  ├─ parse_response()
    │  └─ _final_values_to_delta() → tool_delta
    │
    ├─ apply_memory_rules(intent)
    │  └─ rule_delta (memory_rules.yaml 기반)
    │
    └─ merge_rule_delta(tool_delta, rule_delta)
       └─ final state_delta
           ↓
WorldStateManager.apply_delta()
    ├─ NPCState.stats Dict 업데이트 (동적 스탯)
    ├─ vars 업데이트
    └─ persist()
        ↓
check_ending()
    └─ condition 평가
        ↓
NarrativeLayer.render_day()
    ├─ _collect_narrative_changes() (동적 스탯 렌더링)
    └─ LLM: day narrative 생성
        ↓
Response
```

---

## 데이터 흐름 (Night Phase)

```
NightController.process()
    ├─ Phase 1: _run_reflections()
    │  └─ perform_reflection() → memory에 저장
    │
    ├─ Phase 2: _run_planning()
    │  └─ update_plan(..., stats: Dict)  ← 🆕 동적 스탯
    │     └─ format_emotion(stats)  ← 🆕 동적 스탯 포맷팅
    │
    ├─ Phase 3: _run_dialogues()
    │  └─ _generate_utterance(..., speaker_stats)  ← 🆕 동적 스탯
    │     └─ format_emotion(speaker_stats)  ← 동적 스탯 포맷팅
    │
    └─ Phase 4: _analyze_impacts()
       └─ analyze_conversation_impact(
            ..., stat_names=assets.get_npc_stat_names()
          )  ← 🆕 동적 스탯 이름 리스트
          └─ parse_stat_changes_text(text, stat_names)
             └─ night_delta["npc_stats"] 누적
              ↓
NightResult(night_delta, night_conversation)
    ↓
WorldStateManager.apply_delta(night_delta)
    └─ NPCState.stats Dict 업데이트 (동적 스탯)
        ↓
check_ending()
    ↓
NarrativeLayer.render_night()
    └─ LLM: night narrative 생성
        ↓
Response
```

---

## 동적 스탯 시스템 (🆕 변경점)

### Before (구 시스템)
```
LLM 프롬프트 (하드코딩):
  "trust, suspicion, fear, humanity 변화를 -2~+2 범위로 답하세요"
                ↓
agents/utils.py:
  format_emotion(trust: int, fear: int, suspicion: int)
  parse_stat_changes_text() → 고정 키 ("trust", "suspicion" 등)
```

### After (새 시스템)
```
YAML (npcs.yaml):
  stats: {affection: 50, fear: 80, humanity: 0}
                ↓
ScenarioAssets.get_npc_stat_names()
  → ["affection", "fear", "humanity"]
                ↓
build_output_format(stat_names)
  → LLM에 "affection, fear, humanity 변화를 -2~+2 범위로 답하세요"
                ↓
agents/utils.py:
  format_emotion(stats: Dict[str, int])
    → f"affection={50}, fear={80}, humanity={0}"

  parse_stat_changes_text(text, stat_names)
    → stat_names 기반 정규식 파싱 + 자동 감지
```

### 전파 경로
```
DayController → tools.py → build_*_prompt(assets)
                             ↓
                        build_output_format(
                          assets.get_npc_stat_names()
                        )

NightController → agents/*.py → format_emotion(stats: Dict)
                → agents/*.py → parse_stat_changes_text(
                                  text, stat_names
                                )
```

---

## 핵심 인터페이스 변경 요약

| 컴포넌트 | 변경 전 | 변경 후 |
|---------|---------|--------|
| `format_emotion()` | `(trust, fear, suspicion)` | `(stats: Dict)` |
| `parse_stat_changes_text()` | `(text)` | `(text, stat_names)` |
| `_generate_utterance()` | `(speaker_trust, fear, suspicion)` | `(speaker_stats)` |
| `generate_dialogue()` | `(npc1_trust, fear, suspicion, npc2_trust, ...)` | `(npc1_stats, npc2_stats)` |
| `update_plan()` | `(npc_trust, fear, suspicion)` | `(stats)` |
| `build_*_prompt()` | `()` | `(assets)` |
| `OUTPUT_FORMAT` | 상수 | `build_output_format(stat_names)` |
| `analyze_conversation_impact()` | `()` | `(stat_names)` |

