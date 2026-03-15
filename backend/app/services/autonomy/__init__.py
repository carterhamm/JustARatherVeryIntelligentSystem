"""JARVIS Phase 3: Full Autonomy — self-managing, self-improving AI system."""

from app.services.autonomy.code_manager import run_code_review_cycle
from app.services.autonomy.awareness import run_awareness_cycle
from app.services.autonomy.proactive import run_proactive_cycle
from app.services.autonomy.self_improvement import run_improvement_cycle, generate_weekly_report

__all__ = [
    "run_code_review_cycle",
    "run_awareness_cycle",
    "run_proactive_cycle",
    "run_improvement_cycle",
    "generate_weekly_report",
]
