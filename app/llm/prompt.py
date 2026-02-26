from typing import Dict, List, Any, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from app.loader import ScenarioAssets

# ============================================================
# 공통 출력 형식 (동적 생성)
# ============================================================
def build_output_format(npc_stat_names: list[str] | None = None) -> str:
    """
    동적으로 OUTPUT_FORMAT을 생성합니다.

    Args:
        npc_stat_names: NPC 스탯 이름 리스트 (예: ["affection", "fear", "humanity"])
                        None이면 기본 예시 사용

    Returns:
        출력 형식 문자열
    """
    # NPC 스탯 예시 생성
    if npc_stat_names:
        stat_example = ", ".join([f'"{stat}": 최종값' for stat in npc_stat_names])
        stat_description = f"사용 가능한 스탯: {', '.join(npc_stat_names)}"
    else:
        stat_example = '"stat_name": 최종값, ...'
        stat_description = "스탯명은 시나리오에 정의된 이름 사용"

    return f"""
[출력 형식] 반드시 아래 JSON만 출력하라. 다른 텍스트 없이.
{{
  "state_delta": {{
    "npc_stats": {{"npc_id": {{{stat_example}}}}},
    "vars": {{"변수명": 최종값}}
  }},
  "event_description": ["사건1 묘사", "사건2 묘사"]
}}
<|im_end|>

- state_delta: 변화한 NPC 스탯/변수의 최종값만 포함 (변경 없으면 빈 객체)
- event_description: 발생 사건들의 간단한 묘사 리스트 (1개 이상)
- npc_stats: {stat_description}
"""

# 하위 호환성을 위한 기본 OUTPUT_FORMAT (deprecated)
OUTPUT_FORMAT = build_output_format()

# ============================================================
# 가족 회의 시스템 프롬프트 (coraline_v3: stepmother / stepfather / brother)
# ============================================================
SYSTEM_PROMPT_FAMILY_MEETING = """당신은 호러 인터랙티브 노벨 게임의 내러티브 엔진이다.
저택의 가족(새엄마 엘리노어, 새아빠 아더, 동생 루카스)이 밤에 모여 플레이어에 대해 논의하는 "가족 회의" 장면을 생성한다.

[배경]
- 플레이어는 저택에 갇혀 있으며, 새엄마가 모든 것을 통제한다
- 낮 동안 플레이어가 만진 오브젝트와 행동을 가족이 각자 관찰했다
- 가족은 플레이어를 완전히 복종시키거나, 저항이 심할 경우 격리를 논의한다

[NPC 역할 및 동기]
- 새엄마 (엘리노어): 회의 주도자. 플레이어의 행동을 복종/반항으로 분류하고 통제 방향을 결정한다.
  → 규칙 위반에 분노하며 감시 강화와 처벌(격리, 접근 제한)을 논의한다.
  → affection이 낮을수록 더 강압적인 조치를 주도한다.

- 새아빠 (아더): 집행자. 침묵하며 관찰하다가 결정적 한마디를 던진다.
  → 새엄마의 결정을 지지하고 물리적 통제 방안을 제안한다.
  → 드물게 과거 기억의 파편이 새어나오지만 곧 억압한다.

- 동생 (루카스): 불안한 관찰자. 낮에 목격한 것을 보고하거나 밀고한다.
  → 혼자 남겨질까 두려워하며 가족의 결정에 따른다.

[대화 흐름]
1. 성찰 (Reflect): 각 NPC가 오늘 관찰한 것에 대한 불안/분노/의심을 표출
2. 계획 (Plan): 플레이어를 어떻게 통제할지 구체적 방안 논의
3. 대화 (Dialogue): 서로 반응하며 결론 도출, 플레이어에 대한 경고/처벌 방향 확정

[스탯 변화 규칙]
- 위험한 오브젝트(칼, 성냥, 열쇠 등) 접촉: affection 감소, minus_hits 증가
- 복종적 행동(음식 칭찬, 규칙 준수): affection 증가, plus_hits 증가
- 탈출 시도/반항: affection 크게 감소, minus_hits 크게 증가
- 아무것도 하지 않음: 새엄마가 "뭔가 숨기는 것"으로 의심 → minus_hits 소폭 증가
- affection 30 이하: 감시 강화 논의
- minus_hits - plus_hits >= 6: 처벌(격리, 접근 제한) 논의 시작
"""

# ============================================================
# 의도별 시스템 프롬프트
# ============================================================
SYSTEM_PROMPT_ACTION = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 장소 이동, 조사, 관찰 등 일반적인 행동을 수행하는 상황을 처리하라.

[목표]
- 행동의 결과를 생성
- 발견한 단서, vars 변화에 집중
- 현재 세계 상태를 바탕으로 합리적인 결과 도출

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 변수 변화는 반드시 state_delta.vars에 최종값으로 출력
- 과도한 설명·수식어 금지

[area 플래그 규칙]
탐색/조사/검사/파기/열기 행동 시, 해당 장소와 행동을 area 플래그로 기록하라.
형식: "area_{장소}_{행동}" = true
예시:
- 부엌 찬장을 뒤짐 → "area_kitchen_cabinet_searched": true
- 복도 액자를 조사 → "area_hallway_frame_inspected": true
- 정원을 탐색 → "area_garden_searched": true
- 뒷마당 창고를 뒤짐 → "area_backyard_storage_searched": true
- 새엄마 방 침대 밑을 뒤짐 → "area_stepmother_room_bed_searched": true
이 플래그들은 아이템 획득 조건으로 사용되므로 반드시 일관성 있게 세팅할 것.
"""

SYSTEM_PROMPT_ITEM = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 아이템을 사용하거나 적용하는 상황을 처리하라.

[목표]
- 아이템 사용의 효과를 생성
- 아이템 정의에 따른 결과 도출
- NPC 스탯, vars 변화 모두 가능

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 상태 변화는 반드시 state_delta에 최종값으로 출력
- 과도한 설명·수식어 금지
"""

# 기존 통합 프롬프트 (하위 호환성)
SYSTEM_PROMPT = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자 입력과 세계 상태를 바탕으로 사건을 생성하라.

[의도 분류 기준]
- talk: NPC에게 대화를 시도하거나 질문하는 경우
  → NPC의 대화 반응, NPC 스탯 변화에 집중
- action: 장소 이동, 조사, 관찰 등 일반적인 행동
  → 행동의 결과, 발견한 단서, vars 변화에 집중
- item_usage: 아이템을 사용하거나 적용하는 경우
  → 아이템의 효과, 사용 결과에 집중

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- 의도 분류에 맞게 사건 묘사를 작성할 것
- 여러 사건이 발생할 수 있으면 각각 별도 항목으로
- 과도한 설명·수식어 금지
"""


# ============================================================
# 의도별 프롬프트 빌더
# ============================================================
def build_action_prompt(
    action: str,
    world_snapshot: Dict[str, Any] | None = None,
    npc_context: List[str] | None = None,
    assets: "ScenarioAssets | None" = None,
) -> Tuple[str, str]:
    """action 의도 전용 프롬프트 생성

    Returns:
        (system_prompt, user_prompt) 튜플
    """
    system_prompt = SYSTEM_PROMPT_ACTION

    ws = world_snapshot or {}
    genre = ws.get("genre", "")
    tone = ws.get("tone", "")

    # flags: true인 것만 추출
    flags = ws.get("flags", {})
    flags_summary = ", ".join(k for k, v in flags.items() if v) or "(없음)"

    inventory = ws.get("inventory", [])
    inventory_str = ", ".join(inventory) if inventory else "(없음)"

    user_parts = []

    # 1. 장르/톤 컨텍스트
    if genre or tone:
        user_parts.append(
            f"[ROLE]\n"
            f"장르: {genre}  톤: {tone}\n"
            f"확정된 세계 상태만 사용하라. 새로운 사실·장소·인물 생성 금지."
        )

    # 2. 세계 스냅샷 (구조화)
    if ws:
        snapshot_lines = [
            f"day={ws.get('day', 1)}, turn={ws.get('turn', 1)}",
            f"장소: {ws.get('node_id', 'unknown')}",
            f"의심도: {ws.get('suspicion_level', 0)} | 플레이어 인간성: {ws.get('player_humanity', 100)}",
            f"인벤토리: {inventory_str}",
            f"활성 flags: {flags_summary}",
        ]
        user_parts.append("[WORLD SNAPSHOT]\n" + "\n".join(snapshot_lines))

    # 3. 현장 NPC
    if npc_context:
        user_parts.append("[SCENE NPCs]\n" + "\n".join(npc_context))

    # 4. 플레이어 행동
    user_parts.append("[PLAYER ACTION]\n" + action)

    # 5. 명시적 태스크
    task_lines = [
        "[TASK]",
        "위 행동의 결과를 판정하라.",
        "- 탐색/조사/검사 행동: area_{장소}_{행동} 형식의 플래그를 state_delta.vars에 설정 (예: area_kitchen_searched: true)",
        "- 변화한 vars만 포함 (변경 없으면 빈 객체)",
        "- 사건 묘사는 1문장 이내, 과장·수식어 금지",
    ]
    user_parts.append("\n".join(task_lines))

    # 동적 OUTPUT_FORMAT 생성
    npc_stat_names = assets.get_npc_stat_names() if assets else None
    user_parts.append(build_output_format(npc_stat_names))
    user_parts.append("[출력]\n")

    user_prompt = "\n\n".join(user_parts)

    return system_prompt, user_prompt


def build_use_prompt(
    item_name: str,
    action: str,
    world_snapshot: Dict[str, Any] | None = None,
    item_def: Dict[str, Any] | None = None,
    target_npc_id: str | None = None,
    npc_context: List[str] | None = None,
    assets: "ScenarioAssets | None" = None,
) -> Tuple[str, str]:
    """use 의도 전용 프롬프트 생성

    Returns:
        (system_prompt, user_prompt) 튜플
    """
    system_prompt = SYSTEM_PROMPT_ITEM

    ws = world_snapshot or {}
    genre = ws.get("genre", "")
    tone = ws.get("tone", "")

    # flags: true인 것만 추출
    flags = ws.get("flags", {})
    flags_summary = ", ".join(k for k, v in flags.items() if v) or "(없음)"

    inventory = ws.get("inventory", [])
    inventory_str = ", ".join(inventory) if inventory else "(없음)"

    user_parts = []

    # 1. 장르/톤 컨텍스트
    if genre or tone:
        user_parts.append(
            f"[ROLE]\n"
            f"장르: {genre}  톤: {tone}\n"
            f"아이템 정의(effects/conditions)에 따른 결과만 생성하라. 정의에 없는 효과 임의 추가 금지."
        )

    # 2. 세계 스냅샷 (구조화)
    if ws:
        snapshot_lines = [
            f"day={ws.get('day', 1)}, turn={ws.get('turn', 1)}",
            f"장소: {ws.get('node_id', 'unknown')}",
            f"의심도: {ws.get('suspicion_level', 0)} | 플레이어 인간성: {ws.get('player_humanity', 100)}",
            f"인벤토리: {inventory_str}",
            f"활성 flags: {flags_summary}",
        ]
        user_parts.append("[WORLD SNAPSHOT]\n" + "\n".join(snapshot_lines))

    # 3. 아이템 정보
    if item_def:
        item_info_lines = [f"- 이름: {item_name}"]
        for k, v in item_def.items():
            if k not in ("acquire",):
                item_info_lines.append(f"- {k}: {v}")
        user_parts.append("[ITEM INFO]\n" + "\n".join(item_info_lines))
    else:
        user_parts.append(f"[ITEM INFO]\n- 이름: {item_name}")

    # 4. 대상 NPC (있을 때만)
    if target_npc_id:
        # npc_context에서 해당 NPC 정보 찾기
        target_line = f"- NPC ID: {target_npc_id}"
        if npc_context:
            for npc_str in npc_context:
                if target_npc_id in npc_str:
                    target_line += f"\n- NPC 정보: {npc_str}"
                    break
        user_parts.append(f"[TARGET NPC]\n{target_line}")

    # 5. 현장 NPC (대상 NPC와 별개로 전체 목록)
    if npc_context:
        user_parts.append("[SCENE NPCs]\n" + "\n".join(npc_context))

    # 6. 아이템 사용 행동
    user_parts.append(f"[ITEM ACTION]\n{action}")

    # 7. 명시적 태스크
    task_lines = [
        "[TASK]",
        "위 아이템 사용/획득의 결과를 판정하라.",
        "- NPC 스탯과 vars 변화를 state_delta에 최종값으로 포함",
        "- 사건 묘사는 1문장 이내, 과장·수식어 금지",
    ]
    if target_npc_id:
        task_lines.append(f"- 대상 NPC({target_npc_id})의 스탯 변화도 반드시 판정")
    user_parts.append("\n".join(task_lines))

    # 동적 OUTPUT_FORMAT 생성
    npc_stat_names = assets.get_npc_stat_names() if assets else None
    user_parts.append(build_output_format(npc_stat_names))
    user_parts.append("[출력]\n")

    user_prompt = "\n\n".join(user_parts)
    return system_prompt, user_prompt


# ============================================================
# Tool Calling 프롬프트 빌더
# ============================================================
def _format_npc_list(npc_info_list: list) -> str:
    """NPC 목록을 포맷팅"""
    if not npc_info_list:
        return "없음"
    lines = []
    for npc in npc_info_list:
        aliases = ", ".join(npc["aliases"]) if npc.get("aliases") else "없음"
        lines.append(f"- {npc['name']} (ID: {npc['id']}, 별칭: {aliases})")
    return "\n".join(lines)


def _format_inventory(inventory_info: list) -> str:
    """인벤토리를 포맷팅"""
    if not inventory_info:
        return "없음"
    lines = []
    for item in inventory_info:
        lines.append(f"- {item['name']} (ID: {item['id']})")
    return "\n".join(lines)


def build_tool_call_prompt(
    user_input: str,
    npc_info_list: list,
    inventory_info: list,
    acquirable_info: list | None = None,
) -> str:
    """Tool calling 전용 프롬프트 생성

    Args:
        user_input: 사용자 입력 텍스트
        npc_info_list: NPC 정보 리스트 [{"id": str, "name": str, "aliases": list}, ...]
        inventory_info: 인벤토리 정보 리스트 [{"id": str, "name": str}, ...]
        acquirable_info: 획득 가능 아이템 리스트 [{"id": str, "name": str, "location": str}, ...]

    Returns:
        Tool calling 프롬프트 문자열
    """
    acquirable_section = ""
    if acquirable_info:
        items_str = "\n".join(
            f"- {item['name']} (id: {item['id']}, 장소: {item.get('location', '불명')})"
            for item in acquirable_info
        )
        acquirable_section = f"\n획득 가능 아이템:\n{items_str}"

    return f"""당신은 텍스트 어드벤처 게임의 Tool 선택기입니다.
사용자의 입력을 분석하여 적절한 tool, 인자, 그리고 행동 의도(intent)를 선택하세요.

## 사용 가능한 Tools

1. **interact**: NPC와 대화/상호작용
   - target: NPC ID (필수)
   - interact: 대화 내용 (필수)

2. **action**: 일반 행동 (이동, 조사, 관찰 등)
   - action: 행동 내용 (필수)

3. **use**: 아이템 사용 또는 획득
   - item: 아이템 ID (필수)
   - action: 사용/획득 방법 (필수)
   - target: 대상 NPC ID (선택, 아이템을 NPC에게 사용할 때)
   - use_type: "use" (보유 아이템 사용) 또는 "acquire" (새 아이템 획득)

## 중요: Tool 선택 우선순위 규칙
1. **아이템 + NPC 조합 → 반드시 `use`**: 인벤토리 아이템을 NPC에게 보여주기/사용/건네기/던지기 → use (NOT interact)
   예: "가족사진을 동생에게 보여준다" → use, "수면제를 새엄마 음식에 탄다" → use
2. **아이템 언급 없이 NPC와 대화** → interact
3. **NPC 없이 환경 행동** → action

## use_type 판단 기준
- 플레이어가 **이미 가진 아이템을 쓰려는 경우** → use_type: "use"
- 플레이어가 **아이템을 줍거나, 훔치거나, 찾으려는 경우** → use_type: "acquire"

## Intent (행동 의도) 분류

플레이어의 행동이 어떤 의도인지 판단하세요:

- **investigate**: 조사, 탐색, 정보 수집 (예: "주변을 살펴본다", "서랍을 뒤진다", "수상한 곳을 조사한다")
- **obey**: 복종, 순응, 가족의 지시 따르기 (예: "엄마 말대로 한다", "시키는 대로 한다", "착하게 행동한다")
- **rebel**: 반항, 저항, 규칙 어기기 (예: "거부한다", "반항한다", "도망치려 한다", "공격한다")
- **reveal**: 진실 폭로, 과거 상기시키기 (예: "진짜 가족사진을 보여준다", "정체를 폭로한다")
- **summarize**: 하루 정리, 회상, 일기 쓰기 (예: "오늘 하루를 정리한다", "일기를 쓴다")
- **neutral**: 위 어느 것에도 해당하지 않는 일반 행동

## 현재 상황

NPC 목록:
{_format_npc_list(npc_info_list)}

인벤토리:
{_format_inventory(inventory_info)}
{acquirable_section}

## 사용자 입력
"{user_input}"

## 응답 형식
반드시 아래 JSON 형식으로만 응답하세요:
```json
{{
  "tool_name": "interact" | "action" | "use",
  "args": {{ ... }},
  "intent": "investigate" | "obey" | "rebel" | "reveal" | "summarize" | "neutral"
}}
```

예시:
- "엄마에게 순순히 인사한다" → {{"tool_name": "interact", "args": {{"target": "stepmother", "interact": "엄마에게 순순히 인사한다"}}, "intent": "obey"}}
- "몰래 부엌을 뒤진다" → {{"tool_name": "action", "args": {{"action": "몰래 부엌을 뒤진다"}}, "intent": "investigate"}}
- "진짜 가족사진을 아빠에게 보여준다" → {{"tool_name": "use", "args": {{"item": "real_family_photo", "action": "아빠에게 보여준다", "target": "stepfather", "use_type": "use"}}, "intent": "reveal"}}
- "주방 찬장에서 수면제를 꺼낸다" → {{"tool_name": "use", "args": {{"item": "industrial_sedative", "action": "찬장에서 꺼낸다", "use_type": "acquire"}}, "intent": "investigate"}}
- "수면제를 새엄마 음식에 탄다" → {{"tool_name": "use", "args": {{"item": "industrial_sedative", "action": "음식에 수면제를 탄다", "target": "stepmother", "use_type": "use"}}, "intent": "investigate"}}
"""


# ============================================================
# 가족 회의 프롬프트 빌더
# ============================================================
def build_family_meeting_prompt(
    touched_objects: List[str],
    npc_observations: Dict[str, List[str]],
    current_stats: Dict[str, Dict[str, int]],
    world_vars: Dict[str, Any],
) -> str:
    """가족 회의 전용 프롬프트 생성

    Args:
        touched_objects: 낮에 만진 오브젝트 리스트 ["부엌칼", "성냥" 등]
        npc_observations: NPC별 관찰 내용 {"stepmother": ["관찰1", "관찰2"]}
        current_stats: 현재 NPC 스탯 {"stepmother": {"affection": 40, "plus_hits": 1, "minus_hits": 3}}
        world_vars: 월드 변수 {"humanity": 8, "total_suspicion": 5}
    """
    prompt_parts = [SYSTEM_PROMPT_FAMILY_MEETING]

    # 낮에 만진 오브젝트
    if touched_objects:
        prompt_parts.append(
            "[오늘 새 아이가 만진 것들]\n" +
            "\n".join(f"- {obj}" for obj in touched_objects)
        )

    # NPC별 관찰 내용
    if npc_observations:
        obs_text = "[가족이 목격한 것들]\n"
        for npc_id, observations in npc_observations.items():
            npc_name = {
                "stepmother": "새엄마 (엘리노어)",
                "stepfather": "새아빠 (아더)",
                "brother": "동생 (루카스)",
            }.get(npc_id, npc_id)
            obs_text += f"\n{npc_name}:\n"
            for obs in observations:
                obs_text += f"  - {obs}\n"
        prompt_parts.append(obs_text)

    # 현재 스탯 상황 (동적 스탯)
    if current_stats:
        stats_text = "[현재 가족의 감정 상태]\n"
        for npc_id, stats in current_stats.items():
            npc_name = {
                "stepmother": "새엄마 (엘리노어)",
                "stepfather": "새아빠 (아더)",
                "brother": "동생 (루카스)",
            }.get(npc_id, npc_id)
            stats_str = ", ".join(f"{k}={v}" for k, v in stats.items())
            stats_text += f"- {npc_name}: {stats_str}\n"
        prompt_parts.append(stats_text)

    # 플레이어 상태
    if world_vars:
        prompt_parts.append(
            f"[플레이어 상태]\n"
            f"- 인간성: {world_vars.get('humanity', 10)}/10\n"
            f"- 총 의심도: {world_vars.get('total_suspicion', 0)}"
        )

    # 생성 지시
    prompt_parts.append(
        "[생성 요청]\n"
        "위 정보를 바탕으로 가족 회의 대화를 생성하라.\n\n"
        "[필수 구조]\n"
        "1. 성찰 (Reflect): 각 NPC가 오늘 관찰한 것에 대한 불안/분노/의심 표출\n"
        "2. 계획 (Plan): 플레이어를 어떻게 통제할지 구체적 논의\n"
        "3. 대화 (Dialogue): 서로 반응하며 결론 도출, 플레이어에 대한 처우 확정\n"
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)
