from typing import Dict, List, Any

# ============================================================
# 공통 출력 형식
# ============================================================
OUTPUT_FORMAT = """
[출력 형식] 반드시 아래 JSON만 출력하라. 다른 텍스트 없이.
{
  "state_delta": {
    "npc_stats": {"npc_id": {"trust": 최종값, "suspicion": 최종값, "fear": 최종값, "humanity": 최종값}},
    "vars": {"변수명": 최종값}
  },
  "event_description": ["사건1 묘사", "사건2 묘사"]
}
<|im_end|>

- state_delta: 변화한 NPC 스탯/변수의 최종값만 포함 (변경 없으면 빈 객체)
- event_description: 발생 사건들의 간단한 묘사 리스트 (1개 이상)
- humanity: 인간성 (호감도가 올라가면 인간성이 떨어짐)
"""

# ============================================================
# 코렐라인 전용 - 가족 회의 프롬프트
# ============================================================
SYSTEM_PROMPT_FAMILY_MEETING = """당신은 호러 인터랙티브 노벨 "코렐라인: 단추 눈의 저택"의 내러티브 엔진이다.
단추 인형 가족(단추엄마, 단추아빠, 단추딸)이 밤에 모여 새 아이(플레이어)에 대해 논의하는 "가족 회의" 장면을 생성한다.

[배경]
- 플레이어는 단추 인형 가족의 집에 갇힌 인간이다
- 가족은 플레이어를 영원히 가족으로 만들고 싶어한다 (눈에 단추를 꿰매는 것)
- 낮 동안 플레이어가 만진 오브젝트(칼, 성냥, 바늘 등)를 가족이 알아챘다
- 플레이어가 탈출하거나 그들을 해치려 한다는 의심이 커지고 있다

[캐릭터 특성]
- 단추엄마: 달콤하지만 집착적. 상냥한 말투 뒤에 광기가 숨어있다. "우리 가족이 되면 영원히 사랑해줄게"
- 단추아빠: 과묵하고 관찰적. 규칙과 처벌을 담당. "가족은 서로에게 비밀이 없어야 해"
- 단추딸: 순진해 보이지만 교활한 밀고자. "새 언니/오빠가 이상해. 왜 나랑 안 놀아줘?"

[대화 톤]
- 표면적으로는 "가족 걱정"이지만 실제로는 감시와 압박
- 격한 감정 변화: 실망, 분노, 서운함, 의심이 섞인 대화
- 플레이어가 무기를 만졌다면 → 심문 수준의 추궁
- 플레이어가 거울을 봤다면 → "아직 인형이 되고 싶지 않은 거야?" 식의 질책

[스탯 변화 규칙]
- 플레이어가 무기(칼, 성냥, 바늘)를 만졌으면: suspicion +3~5, trust -1~2
- 플레이어가 거울을 봤으면: humanity +1 (인간성 회복), trust -1
- 플레이어가 가족사진/단추상자를 만졌으면: trust +1, humanity -1
- 의심도(suspicion)가 10 이상이면 처벌 논의 시작

[중요]
- 대화는 불안하고 으스스하게
- 가족의 "사랑"이 실제로는 소유욕과 광기임을 암시
- 플레이어가 느낄 공포와 긴장감을 극대화
"""

# ============================================================
# 의도별 시스템 프롬프트
# ============================================================
SYSTEM_PROMPT_TALK = """당신은 인터랙티브 노벨 게임의 내러티브 엔진이다.
사용자가 NPC에게 대화를 시도하거나 질문하는 상황을 처리하라.

[목표]
- NPC의 대화 반응을 생성
- trust/suspicion/fear 변화에 집중
- NPC의 성격, 기억, 현재 감정 상태를 반영

[규칙]
- 사건 묘사는 최대한 짧고 핵심만 담을 것 (한 문장 이내 권장)
- NPC 스탯 변화는 반드시 state_delta.npc_stats에 최종값으로 출력
- 과도한 설명·수식어 금지
"""

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
  → NPC의 대화 반응, trust/suspicion 변화에 집중
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
def build_talk_prompt(
    message: str,
    user_memory: Dict[str, Any] | None = None,
    npc_memory: Dict[str, Any] | None = None,
    npc_context: List[str] | None = None,
    world_state: Dict | None = None,
) -> str:
    """talk 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_TALK]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if user_memory:
        prompt_parts.append(
            "[사용자 기억]\n" +
            "\n".join(f"- {k}: {v}" for k, v in user_memory.items())
        )

    if npc_memory:
        prompt_parts.append(
            "[NPC 기억]\n" +
            "\n".join(f"- {k}: {v}" for k, v in npc_memory.items())
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[대화 내용]\n" + message
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


def build_action_prompt(
    action: str,
    user_state: Dict[str, Any] | None = None,
    world_state: Dict | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """action 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_ACTION]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if user_state:
        prompt_parts.append(
            "[사용자 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in user_state.items())
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[행동]\n" + action
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


def build_item_prompt(
    item_name: str,
    item_def: Dict[str, Any] | None = None,
    world_state: Dict | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """item 의도 전용 프롬프트 생성"""
    prompt_parts = [SYSTEM_PROMPT_ITEM]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if item_def:
        prompt_parts.append(
            "[아이템 정보]\n" +
            f"- 이름: {item_name}\n" +
            "\n".join(f"- {k}: {v}" for k, v in item_def.items())
        )
    else:
        prompt_parts.append(
            "[아이템 정보]\n" +
            f"- 이름: {item_name}"
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[아이템 사용]\n" + f"{item_name}을(를) 사용한다"
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


# ============================================================
# 기존 통합 프롬프트 빌더 (하위 호환성)
# ============================================================
def build_prompt(
    user_input: str,
    world_state: Dict,
    memory_summary: str | None = None,
    npc_context: List[str] | None = None,
) -> str:
    """프롬프트 생성 (기존 통합 방식)"""
    prompt_parts = [SYSTEM_PROMPT]

    if world_state:
        prompt_parts.append(
            "[세계 상태]\n" +
            "\n".join(f"- {k}: {v}" for k, v in world_state.items())
        )

    if memory_summary:
        prompt_parts.append(
            "[이전 요약]\n" + memory_summary
        )

    if npc_context:
        prompt_parts.append(
            "[등장인물]\n" + "\n".join(npc_context)
        )

    prompt_parts.append(
        "[사용자 입력]\n" + user_input
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)


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

    # 현재 스탯 상황
    if current_stats:
        stats_text = "[현재 가족의 감정 상태]\n"
        for npc_id, stats in current_stats.items():
            npc_name = {
                "button_mother": "단추엄마",
                "button_father": "단추아빠",
                "button_daughter": "단추딸"
            }.get(npc_id, npc_id)
            stats_text += f"- {npc_name}: 호감도={stats.get('trust', 0)}, 의심도={stats.get('suspicion', 0)}\n"
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
        "위 정보를 바탕으로 가족 회의 대화를 생성하라.\n"
        "- 각 NPC가 번갈아가며 발언 (3~5 라운드)\n"
        "- 플레이어의 행동에 대한 격한 반응\n"
        "- 스탯 변화 결정 (state_delta에 포함)"
    )

    prompt_parts.append(OUTPUT_FORMAT)
    prompt_parts.append("[출력]\n")

    return "\n\n".join(prompt_parts)
