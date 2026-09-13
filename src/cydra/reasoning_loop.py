"""End-to-end contradiction reasoning loop: re-evaluate -> belief update -> current belief."""
from __future__ import annotations
from dataclasses import dataclass
from .contradiction_belief import ContradictionBeliefUpdate, apply_current_belief, persist_contradiction_belief_update, update_contradiction_belief
from .contradiction_re_evaluation import ReEvaluation, reevaluate_contradiction
from .contradiction_re_evaluation_model import persist_re_evaluation
from .system_model import SystemModel

@dataclass(frozen=True)
class ReasoningLoopResult:
    re_evaluation: ReEvaluation
    belief_update: ContradictionBeliefUpdate
    current_confidence: float


def run_reasoning_loop(model: SystemModel, *, contradiction_id: str, evidence_id: str, belief_id: str, prior_confidence: float, supports_hypothesis: bool | None, re_evaluation_id: str, belief_update_id: str) -> ReasoningLoopResult:
    reevaluation = reevaluate_contradiction(contradiction_id, evidence_id, supports_hypothesis=supports_hypothesis)
    persist_re_evaluation(model, reevaluation, re_evaluation_id)
    update = update_contradiction_belief(belief_id, contradiction_id, prior_confidence, reevaluation.disposition, evidence_id)
    persist_contradiction_belief_update(model, update, belief_update_id)
    current = apply_current_belief(model, update, belief_update_id)
    return ReasoningLoopResult(reevaluation, update, current)
