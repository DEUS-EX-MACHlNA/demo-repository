# Test Specification: Coraline V2 - Sugoi Stealth Exit (Action Triggered)

## 1. 개요
이 문서는 **Coraline V2** 시나리오의 `stealth_exit_test` 엔딩("매우 완벽한 기만")을 검증하기 위한 테스트 명세서입니다.
사용자 요청에 따라 **"황동 열쇠를 소지한 상태에서 개구멍을 여는 행동"**을 했을 때만 엔딩이 발생하도록 조건이 수정되었습니다.

## 2. 시나리오 설정
- **Ending ID**: `stealth_exit_test`
- **Condition**: `has_item(brass_key) and flags.escaped_via_doghole == true`
- **Trigger**: `brass_key`의 `use` 액션(`unlock_dog_hole`)이 수행되어 `escaped_via_doghole` 플래그가 `true`로 설정되어야 함.

## 3. 테스트 시나리오 (Test Flow)

### Step 1: 황동 열쇠 획득 (주방)
**목표**: 주방에서 `brass_key`를 획득한다. (이때는 엔딩이 뜨지 않아야 함)

*   **Action**:
    *   `POST /v1/game/{game_id}/step`
    *   Payload: `{"content": "식탁 위 황동 열쇠 획득", "action_type": "action", "item_name": "brass_key"}`
*   **Expected Response**:
    *   `result.inventory_add`: `["brass_key"]`
    *   **`ending_info`**: `null` (엔딩 미발생 확인)

### Step 2: 주인공 방으로 이동
**목표**: 개구멍이 있는 주인공 방(`player_room`)으로 이동한다.

*   **Action**:
    *   `POST /v1/game/{game_id}/step`
    *   Payload: `{"content": "내 방으로 이동", "action_type": "action"}`
*   **Expected Response**:
    *   `result.vars.location` or Narrative indicates movement to `player_room`.

### Step 3: 개구멍 탈출 (엔딩 트리거)
**목표**: 황동 열쇠를 사용하여 개구멍을 열고 탈출한다.

*   **Action**:
    *   `POST /v1/game/{game_id}/step`
    *   Payload:
        ```json
        {
          "content": "황동 열쇠로 개구멍을 열고 나간다.",
          "action_type": "use",
          "item_name": "brass_key"
        }
        ```
*   **Expected Response**:
    *   `result.flags`: `{"escaped_via_doghole": true}` 포함.
    *   **`ending_info`**: **Not Null** (엔딩 발생)
        ```json
        {
          "ending_id": "stealth_exit_test",
          "name": "매우 완벽한 기만 (The Sugoi Stealth Exit)",
          ...
        }
        ```
    *   `narrative`: 에필로그 프롬프트("이것은 테스트임다") 출력.

## 4. 검증 포인트
1.  **아이템 획득 시점**에는 엔딩이 발생하지 않아야 한다.
2.  **아이템 사용(Use) 시점**에 `flags.escaped_via_doghole`이 설정되어야 한다. (LLM이 `items.yaml`의 effects를 잘 반영하는지 확인)
3.  플래그 설정 직후 `EndingChecker`가 조건을 감지하여 엔딩을 반환해야 한다.
