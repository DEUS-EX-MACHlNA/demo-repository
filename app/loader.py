"""
app/loader.py
YAML 파일 로더 및 ScenarioAssets 데이터클래스
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ============================================================
# ScenarioAssets: 로드된 모든 YAML 데이터를 담는 컨테이너
# ============================================================
@dataclass
class ScenarioAssets:
    """시나리오의 모든 에셋을 담는 데이터클래스"""
    scenario_id: str
    scenario: dict[str, Any] = field(default_factory=dict)
    story_graph: dict[str, Any] = field(default_factory=dict)
    npcs: dict[str, Any] = field(default_factory=dict)
    items: dict[str, Any] = field(default_factory=dict)
    memory_rules: dict[str, Any] = field(default_factory=dict)

    # 추가 에셋 (locks.yaml 등)
    extras: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_npc_by_id(self, npc_id: str) -> Optional[dict[str, Any]]:
        """NPC ID로 NPC 정보 조회"""
        npcs_list = self.npcs.get("npcs", [])
        for npc in npcs_list:
            if npc.get("npc_id") == npc_id:
                return npc
        return None

    def get_item_by_id(self, item_id: str) -> Optional[dict[str, Any]]:
        """Item ID로 아이템 정보 조회"""
        items_list = self.items.get("items", [])
        for item in items_list:
            if item.get("item_id") == item_id:
                return item
        return None

    def get_node_by_id(self, node_id: str) -> Optional[dict[str, Any]]:
        """Node ID로 스토리 노드 조회"""
        nodes = self.story_graph.get("nodes", [])
        for node in nodes:
            if node.get("node_id") == node_id:
                return node
        return None

    def get_all_npc_ids(self) -> list[str]:
        """모든 NPC ID 목록 반환"""
        return [npc.get("npc_id") for npc in self.npcs.get("npcs", [])]

    def get_all_item_ids(self) -> list[str]:
        """모든 아이템 ID 목록 반환"""
        return [item.get("item_id") for item in self.items.get("items", [])]

    def get_initial_inventory(self) -> list[str]:
        """시작 시 획득하는 아이템 ID 목록"""
        items_list = self.items.get("items", [])
        return [
            item.get("item_id")
            for item in items_list
            if item.get("acquire", {}).get("method") == "start"
        ]

    def get_turn_limit(self) -> int:
        """턴 제한 반환"""
        return self.scenario.get("turn_limit", 12)

    def get_opening_scene_id(self) -> str:
        """시작 씬 ID 반환"""
        return self.scenario.get("opening_scene_id", "act1_open")

    def get_state_schema(self) -> dict[str, Any]:
        """상태 스키마 반환"""
        return self.scenario.get("state_schema", {})


# ============================================================
# ScenarioLoader: YAML 파일을 로드하는 로더
# ============================================================
class ScenarioLoader:
    """시나리오 YAML 파일들을 로드하는 로더"""

    # 필수 파일 목록
    REQUIRED_FILES = [
        "scenario.yaml",
        "story_graph.yaml",
        "npcs.yaml",
        "items.yaml",
        "memory_rules.yaml"
    ]

    # 선택적 파일 목록
    OPTIONAL_FILES = [
        "locks.yaml"
    ]

    def __init__(self, base_path: str | Path = "scenarios"):
        """
        Args:
            base_path: 시나리오들이 위치한 기본 경로
        """
        self.base_path = Path(base_path)

    def _get_scenario_path(self, scenario_id: str) -> Path:
        """시나리오 ID로 디렉토리 경로 생성"""
        return self.base_path / scenario_id

    def _load_yaml_file(self, file_path: Path) -> dict[str, Any]:
        """단일 YAML 파일 로드"""
        if not file_path.exists():
            logger.warning(f"YAML file not found: {file_path}")
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if data is not None else {}
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            raise

    def load(self, scenario_id: str) -> ScenarioAssets:
        """
        시나리오 ID로 모든 YAML 파일을 로드하여 ScenarioAssets 반환

        Args:
            scenario_id: 로드할 시나리오 ID

        Returns:
            ScenarioAssets: 로드된 모든 에셋

        Raises:
            FileNotFoundError: 필수 파일이 없을 때
            yaml.YAMLError: YAML 파싱 실패 시
        """
        scenario_path = self._get_scenario_path(scenario_id)

        if not scenario_path.exists():
            raise FileNotFoundError(f"Scenario directory not found: {scenario_path}")

        logger.info(f"Loading scenario assets from: {scenario_path}")

        # 필수 파일 로드
        scenario = self._load_yaml_file(scenario_path / "scenario.yaml")
        story_graph = self._load_yaml_file(scenario_path / "story_graph.yaml")
        npcs = self._load_yaml_file(scenario_path / "npcs.yaml")
        items = self._load_yaml_file(scenario_path / "items.yaml")
        memory_rules = self._load_yaml_file(scenario_path / "memory_rules.yaml")

        # 필수 파일 검증
        missing_files = []
        for filename in self.REQUIRED_FILES:
            if not (scenario_path / filename).exists():
                missing_files.append(filename)

        if missing_files:
            logger.warning(f"Missing required files for scenario '{scenario_id}': {missing_files}")

        # 선택적 파일 로드
        extras = {}
        for filename in self.OPTIONAL_FILES:
            file_path = scenario_path / filename
            if file_path.exists():
                key = filename.replace(".yaml", "")
                extras[key] = self._load_yaml_file(file_path)

        assets = ScenarioAssets(
            scenario_id=scenario_id,
            scenario=scenario,
            story_graph=story_graph,
            npcs=npcs,
            items=items,
            memory_rules=memory_rules,
            extras=extras
        )

        logger.info(
            f"Loaded scenario '{scenario_id}': "
            f"{len(assets.get_all_npc_ids())} NPCs, "
            f"{len(assets.get_all_item_ids())} items, "
            f"{len(story_graph.get('nodes', []))} story nodes"
        )

        return assets

    def exists(self, scenario_id: str) -> bool:
        """시나리오가 존재하는지 확인"""
        scenario_path = self._get_scenario_path(scenario_id)
        return scenario_path.exists() and (scenario_path / "scenario.yaml").exists()

    def list_scenarios(self) -> list[str]:
        """사용 가능한 모든 시나리오 ID 목록 반환"""
        if not self.base_path.exists():
            return []

        scenarios = []
        for path in self.base_path.iterdir():
            if path.is_dir() and (path / "scenario.yaml").exists():
                scenarios.append(path.name)
        return sorted(scenarios)


# ============================================================
# Singleton-like 캐시된 로더 인스턴스
# ============================================================
_loader_instance: Optional[ScenarioLoader] = None
_assets_cache: dict[str, ScenarioAssets] = {}


def get_loader(base_path: str | Path = "scenarios") -> ScenarioLoader:
    """ScenarioLoader 싱글턴 인스턴스 반환"""
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = ScenarioLoader(base_path)
    return _loader_instance


def load_scenario_assets(scenario_id: str, use_cache: bool = True) -> ScenarioAssets:
    """
    시나리오 에셋 로드 (캐싱 지원)

    Args:
        scenario_id: 시나리오 ID
        use_cache: 캐시 사용 여부

    Returns:
        ScenarioAssets
    """
    global _assets_cache

    if use_cache and scenario_id in _assets_cache:
        logger.debug(f"Using cached assets for scenario: {scenario_id}")
        return _assets_cache[scenario_id]

    loader = get_loader()
    assets = loader.load(scenario_id)

    if use_cache:
        _assets_cache[scenario_id] = assets

    return assets


def clear_assets_cache(scenario_id: Optional[str] = None):
    """에셋 캐시 클리어"""
    global _assets_cache
    if scenario_id:
        _assets_cache.pop(scenario_id, None)
    else:
        _assets_cache.clear()


# ============================================================
# 독립 실행 테스트
# ============================================================
if __name__ == "__main__":
    import json
    from pathlib import Path

    print("=" * 60)
    print("LOADER 컴포넌트 테스트")
    print("=" * 60)

    # 시나리오 경로 설정
    base_path = Path(__file__).parent.parent / "scenarios"
    print(f"\n[1] 시나리오 기본 경로: {base_path}")

    # 로더 생성
    loader = ScenarioLoader(base_path)

    # 사용 가능한 시나리오 목록
    scenarios = loader.list_scenarios()
    print(f"\n[2] 사용 가능한 시나리오: {scenarios}")

    if not scenarios:
        print("❌ 시나리오가 없습니다!")
        exit(1)

    # 첫 번째 시나리오 로드
    scenario_id = scenarios[0]
    print(f"\n[3] 시나리오 로드: {scenario_id}")

    assets = loader.load(scenario_id)

    print(f"\n[4] 로드 결과:")
    print(f"    - scenario_id: {assets.scenario_id}")
    print(f"    - title: {assets.scenario.get('title', 'N/A')}")
    print(f"    - genre: {assets.scenario.get('genre', 'N/A')}")
    print(f"    - turn_limit: {assets.get_turn_limit()}")
    print(f"    - opening_scene: {assets.get_opening_scene_id()}")

    print(f"\n[5] NPCs ({len(assets.get_all_npc_ids())}개):")
    for npc_id in assets.get_all_npc_ids():
        npc = assets.get_npc_by_id(npc_id)
        print(f"    - {npc_id}: {npc.get('name', 'N/A')} ({npc.get('role', 'N/A')})")

    print(f"\n[6] Items ({len(assets.get_all_item_ids())}개):")
    for item_id in assets.get_all_item_ids():
        item = assets.get_item_by_id(item_id)
        print(f"    - {item_id}: {item.get('name', 'N/A')} ({item.get('type', 'N/A')})")

    print(f"\n[7] 초기 인벤토리: {assets.get_initial_inventory()}")

    print(f"\n[8] Story Graph 노드:")
    for node in assets.story_graph.get("nodes", []):
        print(f"    - {node.get('node_id')}: {node.get('summary', 'N/A')[:40]}...")

    print(f"\n[9] State Schema:")
    schema = assets.get_state_schema()
    print(f"    vars: {list(schema.get('vars', {}).keys())}")
    print(f"    flags: {list(schema.get('flags', {}).keys())}")

    print("\n" + "=" * 60)
    print("✅ LOADER 테스트 완료")
    print("=" * 60)
