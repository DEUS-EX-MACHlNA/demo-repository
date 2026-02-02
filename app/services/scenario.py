# 이는 추후에 gameService로 바뀔 예정입니다
# 일단 테스트용으로 간략하게 만들 예정이라 repository도 여기에 넣어 둘 생각입니다

# 1. 일단 요청 받은 id를 기준으로 scenario 데이터를 DB에서 가져옵니다

from __future__ import annotations
import sys
from pathlib import Path
from typing import Union

# 프로젝트 루트를 sys.path에 추가 (직접 실행 시 'app' 패키지 import 문제 해결)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
	sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.db_models.scenario import Scenario
from app.db_models.game import Games, GameStatus
import json
import copy


def extract_initial_npc_data(world_data: dict) -> dict:
	"""
	world_data에서 NPC 초기 상태 데이터를 추출합니다.
	"""
	
	source_npcs = world_data.get("npcs", {}).get("npcs", [])
	
	# 시나리오의 시작 위치 (예: "act1_open") 가져오기
	# world_data 구조: { "scenario": { "opening_scene_id": "...", ... }, ... }
	default_start_node = world_data.get("scenario", {}).get("opening_scene_id")
	
	initial_npc_data = {}
	
	for npc in source_npcs:
		npc_id = npc["npc_id"]
		
		initial_npc_data[npc_id] = {
			# 1. Stats
			"stats": npc.get("stats", {}),
			
			# 2. Status & Memory
			"status": "active",
			"memory": {},
			
			# 3. Persona
			"persona": npc.get("persona", {}),
			
			# 4. 현재 위치 (Current Node)
			# YAML에 'start_node'라고 적어뒀다면 그걸 쓰고,
			# 없으면 시나리오 오프닝 장소에 배치
			"current_node": npc.get("start_node", default_start_node)
		}
		
	return initial_npc_data


def extract_initial_player_data(world_data: dict) -> dict:
	"""
	Scenario 데이터(world_data)를 기반으로 
	Game 생성 시점의 초기 'player_data' JSON을 생성합니다.
	
	Args:
		world_data: scenario.default_world_data (JSONB)
	
	Returns:
		dict: {current_node, inventory, memo, history, objective}
	"""
	
	# 1. 안전하게 데이터 접근
	scenario_meta = world_data.get("scenario", {})
	items_source = world_data.get("items", {}).get("items", [])
	
	# [1] 시작 위치 (current_node)
	# 시나리오에 정의된 오프닝 씬 ID를 가져옵니다.
	start_node = scenario_meta.get("opening_scene_id", "act1_open")
	
	# [2] 초기 인벤토리 (inventory)
	# 아이템 목록 중 획득 조건(acquire.method)이 'start'인 것만 골라냅니다.
	start_inventory = [
		item["item_id"]
		for item in items_source
		if item.get("acquire", {}).get("method") == "start"
	]
	
	# [3] 초기 메모 (memo)
	# 게임 시작 시점엔 기본적으로 빈 리스트입니다.
	# 시나리오에 'initial_memos'가 정의되어 있다면 추가합니다. (튜토리얼용 등)
	initial_memos = []
	
	if "initial_memos" in scenario_meta:
		for idx, memo_text in enumerate(scenario_meta["initial_memos"], 1):
			initial_memos.append({
				"id": idx,
				"text": memo_text,
				"created_at_turn": 0  # 0턴(시작 전)에 생성됨
			})

	
	# -------------------------------------------------------
	# [5] 최종 결과 반환
	# -------------------------------------------------------
	return {
		"current_node": start_node,
		"inventory": start_inventory,
		"memo": initial_memos,
	}


def extract_initial_world_snapshot(world_data: dict) -> dict:
	"""
	Scenario 원본 데이터(world_data)를 기반으로
	게임 실행에 필요한 모든 데이터와 상태를 포함한 'Full Snapshot'을 생성합니다.
	
	Args:
		world_data: scenario.default_world_data (JSONB)
	
	Returns:
		dict: {meta, state, definitions, rules, content}
	"""
	
	# 원본 데이터 접근 (안전하게 get 사용)
	scenario_meta = world_data.get("scenario", {})
	state_schema = scenario_meta.get("state_schema", {})
	
	# =========================================================
	# 1. [State] 변하는 상태값 초기화 (Vars, Flags, System)
	# =========================================================
	
	# (1) Vars: 스키마의 default 값으로 초기화
	initial_vars = {}
	if "vars" in state_schema:
		for key, spec in state_schema["vars"].items():
			initial_vars[key] = spec.get("default", 0)
			
	# (2) Flags: 스키마의 default 값으로 초기화
	initial_flags = {}
	if "flags" in state_schema:
		for key, spec in state_schema["flags"].items():
			initial_flags[key] = spec.get("default", None)
			
	# [중요] Act는 로직상 1로 시작하도록 강제 설정
	initial_flags["act"] = 1
	
	# (3) System: 턴 정보 초기화
	initial_system = {
		"turn": state_schema.get("system", {}).get("turn", {}).get("default", 1),
		"turn_limit": scenario_meta.get("turn_limit", 12)
	}

	# =========================================================
	# 2. [Definitions] 정적 데이터 박제 (Items, Locks)
	#    - 검색 속도를 위해 List -> Dict {id: data} 변환 저장
	# =========================================================
	
	definitions = {}
	
	# (1) Items: 아이템 ID를 키로 변환
	source_items = world_data.get("items", {}).get("items", [])
	definitions["items"] = {}
	for item in source_items:
		# 원본 오염 방지를 위해 deepcopy
		item_copy = copy.deepcopy(item)
		definitions["items"][item["item_id"]] = item_copy
		
	# (2) Locks: 락 ID를 키로 변환 + 초기 상태(is_unlocked) 설정
	source_locks = world_data.get("extras", {}).get("locks", {}).get("locks", [])
	definitions["locks"] = {}
	for lock in source_locks:
		lock_copy = copy.deepcopy(lock)
		# 스냅샷 생성 시점엔 무조건 잠김 상태로 시작
		lock_copy["is_unlocked"] = False
		definitions["locks"][lock["info_id"]] = lock_copy

	# =========================================================
	# 3. [Rules & Meta] 규칙 및 메타데이터 복사
	# =========================================================
	
	# 승리/패배 조건 및 엔딩 정의
	rules = {
		"victory_conditions": scenario_meta.get("victory_conditions", []),
		"failure_conditions": scenario_meta.get("failure_conditions", []),
		"endings": scenario_meta.get("endings", []),
		# AI 기억 조작 룰 (memory_rules가 scenario 안에 있다고 가정)
		"memory_rules": scenario_meta.get("memory_rules", {}) 
	}
	
	# 게임 메타 정보 (타이틀, 장르, 절대 규칙 등)
	meta = {
		"title": scenario_meta.get("title", ""),
		"genre": scenario_meta.get("genre", ""),
		"global_rules": scenario_meta.get("global_rules", [])
	}

	# =========================================================
	# 4. [Content] 스토리 그래프 (Map Structure)
	# =========================================================
	content = {
		"story_graph": world_data.get("story_graph", {}).get("nodes", [])
	}

	# =========================================================
	# 5. 최종 조립 및 반환
	# =========================================================
	return {
		"meta": meta,
		"state": {
			"system": initial_system,
			"vars": initial_vars,
			"flags": initial_flags
		},
		"definitions": definitions,
		"rules": rules,
		"content": content
	}


def get_scenario_json(scenario_id: int) -> dict:
	"""
	주어진 시나리오 식별자에 대해 DB에서 `base_system_prompt`와
	`default_world_data`를 반환합니다.

	Args:
		scenario_id: 정수형 PK(id) 또는 시나리오 문자열 식별자(title)

	Returns:
		dict: {"base_system_prompt": ..., "default_world_data": ...}

	Raises:
		ValueError: 해당 시나리오를 찾을 수 없을 때
	"""
	db = SessionLocal()
	try:
		# 정수면 PK로 조회, 아니면 title로 조회
		if isinstance(scenario_id, int):
			scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
		if not scenario:
			raise ValueError(f"Scenario not found: {scenario_id}")
		return {
			"base_system_prompt": scenario.base_system_prompt,
			"default_world_data": scenario.default_world_data,
		}
	finally:
		db.close()


# 여기가 본진
def create_game_for_scenario(scenario_id: int, user_id: int = 1) -> int:
	"""
	주어진 시나리오 ID로 새로운 게임 레코드를 생성합니다.
	`npc_data`는 `default_world_data`에서 자동으로 추출됩니다.
	나머지 필드(`player_data`, `summary`)는 추후 단계별로 채워질 예정입니다.

	Args:
		scenario_id: 생성할 게임과 연결할 시나리오의 PK
		user_id: 게임을 생성한 사용자 ID (기본값 1)

	Returns:
		int: 생성된 `Games.id`

	Raises:
		ValueError: 지정한 시나리오가 존재하지 않을 때
	"""
	db = SessionLocal()
	try:
		scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
		if not scenario:
			raise ValueError(f"Scenario not found: {scenario_id}")

		# default_world_data에서 데이터 추출
		default_world = scenario.default_world_data or {}
		npc_data = extract_initial_npc_data(default_world)
		player_data = extract_initial_player_data(default_world)
		world_snapshot = extract_initial_world_snapshot(default_world)
		
		# TODO 여기에 summary 생성 로직 추가
		#summary = 여기에 summary 생성 로직 추가
		
		game = Games(
			scenarios_id=scenario.id,
			user_id=user_id,
			world_data_snapshot=world_snapshot,
			player_data=player_data,
			npc_data=npc_data,
			summary={},  # TODO: 이 부분은 추후 LLM에 넣어 둘 내용을 의미
			status=GameStatus.LIVE,
		)
		db.add(game)
		db.commit()
		db.refresh(game)
		return game.id
	finally:
		db.close()




# if __name__ == "__main__":
# 	# 게임 생성 테스트
	
# 	try:
# 		print("=" * 60)
# 		print("게임 생성 테스트 시작")
# 		print("=" * 60)
		
# 		# 시나리오 ID 1로 게임 생성
# 		game_id = create_game_for_scenario(scenario_id=1, user_id=1)
		
# 		print(f"\n✓ 게임 생성 성공!")
# 		print(f"생성된 Game ID: {game_id}")
# 		print("\n게임이 DB에 저장되었습니다.")
# 		print("저장된 데이터:")
# 		print(f"  - npc_data: NPC 초기 상태 데이터")
# 		print(f"  - player_data: 플레이어 초기 상태 (위치, 인벤토리, 메모)")
# 		print(f"  - world_data_snapshot: 게임 월드 전체 스냅샷 (state, definitions, rules, content)")
# 		print(f"  - status: {GameStatus.LIVE}")
		
# 	except Exception as e:
# 		print(f"✗ 게임 생성 실패: {e}")
# 		import traceback
# 		traceback.print_exc()