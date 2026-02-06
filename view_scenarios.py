"""
view_scenarios.py
DB의 scenarios 테이블 데이터 조회 및 출력
그냥 임시방편입니다 지우셔도 상관 무무
"""
import sys
from pathlib import Path
import json

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.database import SessionLocal
from app.db_models.scenario import Scenario


def view_all_scenarios():
    """DB의 모든 scenarios 출력"""
    db = SessionLocal()
    try:
        scenarios = db.query(Scenario).all()
        
        if not scenarios:
            print("❌ No scenarios found in database")
            return
        
        print("=" * 80)
        print(f"✓ Total scenarios: {len(scenarios)}")
        print("=" * 80)
        
        for scenario in scenarios:
            print(f"\n📋 Scenario ID: {scenario.id}")
            print(f"   Title: {scenario.title}")
            print(f"   Created: {scenario.create_time}")
            print(f"   Updated: {scenario.update_time}")
            
            print(f"\n   📌 Base System Prompt:")
            print(f"      {json.dumps(scenario.base_system_prompt, indent=6, ensure_ascii=False)}")
            
            print(f"\n   🌍 Default World Data:")
            # 전체 값을 보기 위해 JSON으로 전체 출력
            print(json.dumps(scenario.default_world_data, indent=3, ensure_ascii=False))
            
            print("\n" + "-" * 80)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        db.close()


def view_scenario_by_id(scenario_id: str):
    """특정 scenario_id의 데이터 출력"""
    db = SessionLocal()
    try:
        scenario = db.query(Scenario).filter(Scenario.title == scenario_id).first()
        
        if not scenario:
            print(f"❌ Scenario '{scenario_id}' not found")
            return
        
        print("=" * 80)
        print(f"✓ Scenario: {scenario_id}")
        print("=" * 80)
        
        print(f"\n📋 Basic Info:")
        print(f"   ID: {scenario.id}")
        print(f"   Title: {scenario.title}")
        print(f"   Created: {scenario.create_time}")
        print(f"   Updated: {scenario.update_time}")
        
        print(f"\n📌 Base System Prompt:")
        print(json.dumps(scenario.base_system_prompt, indent=3, ensure_ascii=False))
        
        print(f"\n🌍 Default World Data:")
        print(json.dumps(scenario.default_world_data, indent=3, ensure_ascii=False))
        
        print("\n" + "=" * 80)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
    finally:
        db.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 특정 scenario_id 조회
        scenario_id = sys.argv[1]
        view_scenario_by_id(scenario_id)
    else:
        # 모든 scenarios 조회
        view_all_scenarios()
