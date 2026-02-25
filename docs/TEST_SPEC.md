# Test Specification ? Component vs Integration (coraline_v3)

본 문서는 `coraline_v3` 시나리오 기준으로 **컴포넌트 테스트**와 **통합(유저 시나리오) 테스트**를 정의한다. 테스트는 **현행 코드 동작**을 기준으로 작성하되, YAML/설계 의도와 어긋나는 지점은 **갭**으로 명시한다.

**범위**
- 대상 코드: `app/services/game.py`, `app/api/routes/v1/game.py`, `app/api/routes/v1/scenario.py`, `app/day_controller.py`, `app/night_controller.py`, `app/lock_manager.py`, `app/ending_checker.py`, `app/item_acquirer.py`, `app/item_acquire_resolver.py`, `app/item_use_resolver.py`, `app/effect_applicator.py`, `app/condition_eval.py`, `app/narrative.py`
- 시나리오 YAML: `scenarios/coraline_v3/*`

**전제/테스트 환경**
- LLM 호출은 스텁/모킹으로 고정 응답을 사용한다.
- 랜덤(`random.choice`)은 시드 고정 또는 선택 로직 모킹으로 결정적으로 만든다.
- Redis ON/OFF 케이스를 분리한다. Redis OFF 시 `get_game_state`는 None을 반환해야 한다.
- DB fixture는 `Scenario`, `Games`를 포함해야 하며 `coraline_v3` 자산이 로드되어야 한다.
- 상태/자산은 가능한 한 YAML 로더(`ScenarioLoader`)를 통해 구성한다.

---

**Part A. 컴포넌트 테스트**

## A1. API 라우트 레벨

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| A1-01 | 게임 목록 반환 | 게임 1개 이상 존재 | `GET /v1/game/` | 리스트 형태, 각 항목에 `game_id`, `summary`, `status` 포함 | 없음 |
| A1-02 | 스텝 처리 정상 | 유효 `game_id` | `POST /v1/game/{id}/step` | `StepResponseSchema` 형식 응답 | **갭:** 라우트가 `GameService.process_turn`의 튜플을 그대로 반환 (스키마 불일치 가능) |
| A1-03 | 스텝 처리 404 | 존재하지 않는 `game_id` | `POST /v1/game/{id}/step` | 404 | 없음 |
| A1-04 | 게임 시작 정상 | 유효 `game_id` | `GET /v1/game/start/{id}` | `GameClientSyncSchema` 반환, Redis 캐싱 시도 | 없음 |
| A1-05 | 게임 시작 404 | 존재하지 않는 `game_id` | `GET /v1/game/start/{id}` | 404 | 없음 |
| A1-06 | 나이트 처리 정상 | 유효 `game_id` | `POST /v1/game/{id}/night_dialogue` | `NightResponseResult` 반환 | 없음 |
| A1-07 | 이동 요청 | Redis ON, player_info 존재 | `POST /v1/game/{id}/move?location=kitchen` | Redis의 `player_info.current_node` 업데이트 | 없음 |
| A1-08 | 시나리오 목록 | YAML 존재 | `GET /v1/scenario/` | `coraline_v3` 포함 | 없음 |
| A1-09 | 시나리오 시작 | DB에 해당 시나리오 존재 | `GET /v1/scenario/start/{scenario_id}?user_id=1` | `GameClientSyncSchema` 반환 | 없음 |

## A2. GameService 파이프라인

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| A2-01 | Redis hit 로드 | Redis ON, `game:{id}:data` 존재 | `process_turn` 호출 | Redis 데이터로 world_state 구성 | 없음 |
| A2-02 | Redis miss 로드 | Redis OFF 또는 캐시 없음 | `process_turn` 호출 | DB 기반 world_state 구성 | 없음 |
| A2-03 | 자산 로드 fallback | DB 자산 없음 | `_scenario_to_assets` | 파일 기반 로드 | 없음 |
| A2-04 | item_states 복원 | `game.player_data.item_states` 존재 | `_scenario_to_assets` | items.yaml 상태 반영 | 없음 |
| A2-05 | LockManager 적용 | locks.yaml 존재 | `process_turn` | `world_state.locks` 업데이트 | 없음 |
| A2-06 | StatusEffect 만료 | `vars.status_effects` 존재 | `process_turn` 시작 | 만료된 효과 제거, status 복구 | 없음 |
| A2-07 | DayController 툴 선택 | LLM 스텁 | `DayController.process` | `interact/action/use` 선택 | 없음 |
| A2-08 | 인벤토리 아이템 감지 | 인벤토리에 아이템 | `interact` 입력 | `use`로 전환 | 없음 |
| A2-09 | RuleEngine intent 반영 | intent 존재 | `process_turn` | vars/npc_stats에 delta 반영 | 없음 |
| A2-10 | turn 증가 | 기본 step 처리 | `process_turn` | `world_state.turn` +1 | 없음 |
| A2-11 | delta 적용 규칙 | 다양한 delta | `_apply_delta` | stats clamp, status/phase, vars min/max, locks/inventory 반영 | 없음 |
| A2-12 | auto 아이템 획득 | auto 조건 충족 | `ItemAcquirer.scan` | inventory_add 발생, 중복 방지 | 없음 |
| A2-13 | day_action_log 기록 | 정상 step | `process_turn` | 로그 엔트리 추가 | 없음 |
| A2-14 | EndingChecker 트리거 | 조건 충족 | `process_turn` | ending_info 설정, 게임 상태 ENDING 설정 | 없음 |
| A2-15 | Narrative 렌더링 | LLM ON/OFF | `process_turn` | 렌더 결과 또는 실패 시 빈 문자열 | 없음 |
| A2-16 | DB 반영 | step 완료 | `_world_state_to_games` | inventory/locks/npc_data/state 반영 | 없음 |
| A2-17 | 아이템 상태 전이 | item acquire/use | `_world_state_to_games` | ACQUIRED/USED 상태 반영 | 없음 |
| A2-18 | night 처리 | 정상 야간 | `process_night` | `vars.day` +1, day_action_log 초기화 | 없음 |

## A3. YAML 규칙 기반 컴포넌트 테스트 (coraline_v3)

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| A3-01 | 아이템 location 기반 획득 실패 | player 위치와 item location 불일치 | acquire 시도 | 실패 메시지 또는 획득 불가 | **갭:** location 조건 평가 로직 없음 |
| A3-02 | `real_family_photo` auto 획득 | `npc.dog_baron.affection >= 90` | `ItemAcquirer.scan` | inventory_add 포함 | 없음 |
| A3-03 | `industrial_sedative` 획득 조건 | `npc.stepmother.status == 'missing'` | acquire 시도 | 성공 메시지 + inventory_add | 없음 |
| A3-04 | `secret_key` 획득 조건 | sleeping 또는 sacrifice | acquire 시도 | 성공 메시지 + inventory_add | 없음 |
| A3-05 | `real_family_photo` 사용 조건 | npc, player location 동일 | use 시도 | 효과 적용 | **갭:** `player.location`, `npc.location` 조건 미지원 |
| A3-06 | `lighter` 사용 조건 | `flags.oil_on_stepmother == true` | use 시도 | `flags.house_on_fire = true` | 없음 |
| A3-07 | lock unlock | 조건 충족 | `LockManager.check_unlocks` | lock 상태 true, memory 주입 | 없음 |
| A3-08 | 승리 엔딩 | 조건 충족 | `EndingChecker.check_ending` | `stealth_exit` 등 트리거 | 없음 |
| A3-09 | 실패 엔딩 | 조건 충족 | `EndingChecker.check_ending` | 실패 엔딩 트리거 | 없음 |
| A3-10 | ConditionEvaluator 패턴 | 지원 패턴 입력 | evaluate | 올바른 bool | 없음 |
| A3-11 | StatusEffect 적용/만료 | duration 있음 | apply + tick | status 변경 후 만료 복구 | 없음 |
| A3-12 | ItemUseResolver 3단계 | 유효 action | resolve | validate/simulate/commit 정상 | 없음 |

---

**Part B. 통합(유저 시나리오) 테스트**

## B1. 게임 목록/시작 플로우

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| B1-01 | 시나리오 목록 조회 | YAML 로더 정상 | `GET /v1/scenario/` | `coraline_v3` 포함 | 없음 |
| B1-02 | 게임 생성 | 유효 scenario_id | `GET /v1/scenario/start/{scenario_id}?user_id=1` | game 생성, Redis 캐시 시도 | 없음 |
| B1-03 | 게임 목록 포함 | B1-02 이후 | `GET /v1/game/` | 생성된 game_id 포함 | 없음 |

## B2. 일/밤 흐름 통합

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| B2-01 | day step 처리 | 유효 game_id | `POST /v1/game/{id}/step` | narrative/state_result 정상 | **갭:** route 반환 스키마 불일치 가능 |
| B2-02 | night 처리 | day 이후 | `POST /v1/game/{id}/night_dialogue` | day 증가, night narrative 생성 | 없음 |

## B3. 승리 엔딩 시나리오

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| B3-01 | Stealth Exit 엔딩 | sedative 확보, stepmother sleeping, secret_key 보유 | step 진행 후 ending 체크 | `stealth_exit` 도달 | **갭:** 위치 조건/획득 조건 일부 미평가 |
| B3-02 | Chaotic Breakout 엔딩 | `oil_bottle` → `lighter` | step 진행 후 ending 체크 | `house_on_fire` 플래그 true → 엔딩 | 없음 |

## B4. 실패 엔딩 시나리오

| ID | 목적 | 사전조건 | 입력/절차 | 기대 결과 | 갭 |
| --- | --- | --- | --- | --- | --- |
| B4-01 | humanity 0 엔딩 | `vars.humanity <= 0` | step 진행 | `unfinished_doll` 도달 | 없음 |
| B4-02 | suspicion 100 엔딩 | `vars.suspicion_level >= 100` | step 진행 | `caught_and_confined` 도달 | 없음 |
| B4-03 | turn_limit 엔딩 | `turn == turn_limit` | step 반복 | `eternal_dinner` 도달 | 없음 |

---

**갭/리스크 요약**

| 구분 | 설명 | 영향 |
| --- | --- | --- |
| API 응답 스키마 | `POST /v1/game/{id}/step`가 `StepResponseSchema` 대신 튜플을 반환할 가능성 | 클라이언트 파싱 실패 가능 |
| location 조건 미지원 | `player.location`, `npc.location`, `acquire.location` 조건을 평가하지 않음 | 위치 기반 획득/사용 규칙 미작동 |
| LLM/랜덤 비결정성 | Tool 선택, 대화/나이트 결과가 비결정적 | 테스트 재현성 저하 |

