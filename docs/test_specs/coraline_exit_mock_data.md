# Mock Data: Coraline V2 - Sugoi Stealth Exit Test

## 중요 알림 (Schema Mismatch)
현재 서버 코드(`app/schemas/request_response.py`)는 `StepRequestSchema`에 대해 다음 필드들을 정의하고 있습니다:
- `content` (과거 `chat_input`)
- `action_type` (필수, default="dialogue")
- `npc_name`, `item_name`

요청하신 `chat_input` 필드는 현재 코드에서 `content`로 리팩토링되었습니다. (Task #20 참조)
아래 Mock Data는 **현직 서버 코드 기준**으로 동작하는 Payload를 작성했습니다.
만약 `chat_input`을 사용하시려면 서버 코드를 롤백해야 합니다.

---

## 1. 황동 열쇠 획득 (Acquire Key)
**상황**: 주방(kitchen)에서 식탁 위의 황동 열쇠를 발견하고 획득함.

### Request (`POST /v1/game/{game_id}/step`)
```json
{
  "content": "식탁 위에 있는 황동 열쇠를 챙긴다.",
  "action_type": "action",
  "item_name": "brass_key"
}
```

### Response (200 OK)
```json
{
  "narrative": "당신은 조심스럽게 식탁으로 다가가 황동 열쇠를 집어들었습니다. 차가운 금속의 감촉이 손끝에 전해집니다. 이제 이 열쇠로 무언가를 열 수 있을 것 같습니다.",
  "ending_info": null,
  "result": {
    "inventory_add": ["brass_key"],
    "vars": {},
    "npc_stats": {}
  },
  "debug": {
    "steps": ["lock_check", "day_turn"]
  }
}
```

---

## 2. 주인공 방으로 이동 (Move to Room)
**상황**: 열쇠를 획득한 후, 개구멍이 있는 주인공 방(`player_room`)으로 이동함.

### Request (`POST /v1/game/{game_id}/step`)
```json
{
  "content": "내 방으로 돌아간다.",
  "action_type": "action"
}
```

### Response (200 OK)
```json
{
  "narrative": "당신은 주방을 빠져나와 복도를 지나, 익숙한 자신의 방으로 돌아왔습니다. 문을 닫자 잠시나마 안도감이 듭니다. 구석에 있는 작은 개구멍이 눈에 띕니다.",
  "ending_info": null,
  "result": {
    "vars": {
      "location": "player_room"
    }
  },
  "debug": {}
}
```

---

## 3. 개구멍 탈출 (Escape / Ending Trigger)
**상황**: 황동 열쇠를 사용하여 개구멍을 열고 탈출을 시도함.
**조건**: `items.yaml`에 정의된 대로 `brass_key` 사용 시 `unlock_exit` 효과가 발생한다고 가정 (User's Step 1412 Revert 반영).
*주의*: 현재 서버 로직상 `unlock_exit` 효과 처리기가 없으므로, 테스트 환경에서는 LLM이 이를 "엔딩 트리거"로 해석하거나, `items.yaml`을 `flags.escaped_via_doghole` 설정으로 유지하는 것이 안전합니다. 아래는 **엔딩이 성공했을 때**의 Mock 입니다.

### Request (`POST /v1/game/{game_id}/step`)
```json
{
  "content": "황동 열쇠로 개구멍을 열고 나간다.",
  "action_type": "use",
  "item_name": "brass_key"
}
```

### Response (200 OK)
```json
{
  "narrative": "이것은 테스트임다",
  "ending_info": {
    "ending_id": "stealth_exit_test",
    "name": "매우 완벽한 기만 (The Sugoi Stealth Exit)",
    "description": "당신은 가족들의 눈을 피해 완벽하게 저택을 탈출했습니다.",
    "condition_met": "has_item(brass_key) and flags.escaped_via_doghole == true"
  },
  "result": {
    "flags": {
      "escaped_via_doghole": true
    },
    "locks": {
      "real_world": false
    }
  },
  "debug": {}
}
```
