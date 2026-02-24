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
# 코렐라인 전용 - 가족 회의 프롬프트
# ============================================================
SYSTEM_PROMPT_FAMILY_MEETING = """당신은 호러 인터랙티브 노벨 "코렐라인: 단추 눈의 저택"의 내러티브 엔진이다.
단추 인형 가족(단추엄마, 단추아빠, 단추딸)이 밤에 모여 새 아이(플레이어)에 대해 논의하는 "가족 회의" 장면을 생성한다.

[핵심 원칙: 극도의 의심]
- 가족은 플레이어의 모든 행동을 의심의 눈으로 본다
- "왜 그걸 만졌지?", "뭘 숨기는 거야?", "우릴 버리려고?" 같은 질문이 끊이지 않는다
- 아무리 무해한 행동도 탈출/반항의 증거로 해석한다
- 플레이어가 아무것도 안 만졌어도 "오늘 왜 이렇게 조용했지? 뭔가 꾸미는 거야?"

[배경]
- 플레이어는 단추 인형 가족의 집에 갇힌 인간이다
- 가족은 플레이어를 영원히 가족으로 만들고 싶어한다 (눈에 단추를 꿰매는 것)
- 낮 동안 플레이어가 만진 오브젝트(칼, 성냥, 바늘 등)를 가족이 알아챘다
- 플레이어가 탈출하거나 그들을 해치려 한다는 의심이 커지고 있다

[캐릭터 특성 - 몬스터 말투]
- 단추엄마: 달콤함과 광기가 급변. "후후... 엄마가 다~ 알아... 네가 뭘 만졌는지... 뭘 생각하는지..."
  → 화나면: "감히...! 이 집에서 나가려고?! 엄마 심장을 찢을 셈이야?!"
  → 성찰: "저 아이의 눈빛이... 아직 우리를 가족으로 안 보는 것 같아... 끔찍해..."

- 단추아빠: 저음의 위협적 말투. "...봤다. 네가 뭘 만졌는지. 다. 봤어."
  → 화나면: "규칙을 어겼군. 처벌이 필요해. 손가락 하나... 아니, 눈부터 시작할까."
  → 계획: "감시를 강화해야 해. 낮에도. 밤에도. 한시도 눈을 떼면 안 돼."

- 단추딸: 섬뜩한 동심. "키키키... 언니/오빠가 칼을 만졌대~ 나쁜 아이~ 혼나야 해~"
  → 밀고: "엄마! 아빠! 새 언니가 거울 봤어! 자기 눈 보면서 울었어! 아직 인형 되기 싫은가봐!"
  → 협박: "나랑 놀아줘... 안 그러면... 엄마한테 다 이를 거야... 히히..."

[대화 흐름 - 성찰/계획/대화 모두 격렬하게]
1. 성찰 (Reflect): 각자 오늘 목격한 것에 대한 불안/분노/의심 표출
   예: "저 아이가 성냥을 만졌어... 우릴 태우려는 거야... 끔찍해... 무서워..."

2. 계획 (Plan): 플레이어를 어떻게 통제할지 논의
   예: "내일은 부엌을 잠가. 도구를 다 숨겨. 아니, 차라리 손을 묶어버릴까?"

3. 대화 (Dialogue): 서로에게 격하게 반응하며 에스컬레이션
   예: "네 잘못이야! 네가 감시를 소홀히 해서!" / "뭐라고?! 감히!"

[스탯 변화 규칙 - 격렬한 반응 = 큰 변화]
- 무기(칼, 성냥, 바늘) 만짐: suspicion +5~8, trust -2~4
- 거울 봄: trust -2~3 (배신감), humanity +1 (플레이어 인간성 회복)
- 가족사진/단추상자 만짐: trust +2, humanity -2 (인형화 가속)
- 아무것도 안 만짐: suspicion +2 ("뭔가 꾸미고 있어")
- 의심도 8 이상: 처벌 논의 시작 ("손가락을 자를까?", "눈을 먼저 꿰맬까?")
- 의심도 12 이상: 즉각 행동 논의 ("오늘 밤 끝내자", "더 기다릴 필요 없어")

[중요: 극대화된 공포]
- 대화는 광기와 집착으로 가득 차게
- "사랑"이라는 단어를 쓸수록 더 무섭게
- 가족끼리도 서로 비난하며 긴장감 고조
- 플레이어에 대한 "처벌" 언급을 구체적으로 (눈 꿰매기, 손 자르기, 가두기 등)
- 회의가 끝날 때 항상 플레이어에게 향하는 위협적 결론으로 마무리
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
# 코렐라인 가족 회의 프롬프트 빌더
# ============================================================
def build_family_meeting_prompt(
    touched_objects: List[str],
    npc_observations: Dict[str, List[str]],
    current_stats: Dict[str, Dict[str, int]],
    world_vars: Dict[str, Any],
) -> str:
    """코렐라인 가족 회의 전용 프롬프트 생성

    Args:
        touched_objects: 낮에 만진 오브젝트 리스트 ["부엌칼", "성냥" 등]
        npc_observations: NPC별 관찰 내용 {"button_mother": ["관찰1", "관찰2"]}
        current_stats: 현재 NPC 스탯 {"button_mother": {"trust": 5, "suspicion": 3}}
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
                "button_mother": "단추엄마",
                "button_father": "단추아빠",
                "button_daughter": "단추딸"
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
                "button_mother": "단추엄마",
                "button_father": "단추아빠",
                "button_daughter": "단추딸"
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
        "1. 성찰 (Reflect): 각 NPC가 오늘 관찰한 것에 대한 불안/분노/배신감 표출\n"
        "2. 계획 (Plan): 플레이어를 어떻게 통제/처벌할지 구체적 논의\n"
        "3. 대화 (Dialogue): 서로 비난하며 에스컬레이션, 결론은 플레이어 위협\n\n"
        "[톤 가이드]\n"
        "- 몬스터 같은 말투: '키키키', '후후후', '...봤다' 등 사용\n" # rule base로 수정하고 프롬프트에서 건드리지 말자
        "- 급격한 감정 변화: 달콤함 → 광기, 침묵 → 폭발\n"
        "- 구체적 처벌 언급: 눈 꿰매기, 손가락 자르기, 가두기 등\n"
        "- 가족끼리도 서로 비난: '네 감시가 부족해서!', '네 잘못이야!'\n\n"
        "[스탯 변화 - 반드시 큰 폭으로]\n"
        "- suspicion은 최소 +3 이상 변화\n"
        "- trust도 최소 ±2 이상 변화\n"
        "- 무기 만졌으면 suspicion +5~8\n"
        "- 아무것도 안 만졌어도 suspicion +2 ('뭔가 꾸미고 있어')\n"
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)
