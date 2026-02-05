from sqlalchemy.orm import Session
from typing import Optional
from app.db_models.scenario import Scenario

def get_scenario_by_id(db: Session, scenario_id: int) -> Optional[Scenario]:
    """Scenario ID로 시나리오 정보를 조회합니다."""
    return db.query(Scenario).filter(Scenario.id == scenario_id).first()
