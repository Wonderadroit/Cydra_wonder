from __future__ import annotations

from .models import Evidence, Experiment, Hypothesis, Invariant, ContractModel


def access_control_invariant(contract: ContractModel, privileged_modifier: str = "onlyGov") -> Invariant:
    return Invariant(
        invariant_id="INV-AUTH-001",
        statement=f"Administrative state-changing operations must enforce {privileged_modifier} authorization.",
        provenance="structural sibling-function rule; modifier-bearing administrative functions",
        confidence=0.90,
    )


def generate_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    admin_functions = [f for f in contract.functions if f.name.startswith(("set", "add", "remove", "update", "accept"))]
    protected = [f for f in admin_functions if f.modifiers]
    if not protected:
        return ()

    invariant = access_control_invariant(contract)
    hypotheses: list[Hypothesis] = []
    for fn in admin_functions:
        if fn.modifiers:
            continue
        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"H-AUTH-{fn.name}",
                claim=f"{fn.name} may permit an unauthorized caller to mutate privileged state.",
                invariant_id=invariant.invariant_id,
                target_function=fn.name,
                attacker_capability="arbitrary external caller",
                expected_impact="privileged configuration or authorization state can be changed",
                evidence_ids=(f"E-MODEL-{fn.name}",),
            )
        )
    return tuple(hypotheses)


def plan_access_control_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(
        experiment_id=f"X-{hypothesis.hypothesis_id}",
        hypothesis_id=hypothesis.hypothesis_id,
        action=(
            f"Execute {hypothesis.target_function} from an unprivileged actor and assert that the "
            "privileged state does not change; then repeat against the patched version."
        ),
        discriminates=("missing authorization is exploitable", "authorization is enforced elsewhere"),
        cost=1.0,
    )


def build_evidence(contract: ContractModel, hypotheses: tuple[Hypothesis, ...]) -> tuple[Evidence, ...]:
    evidence = []
    for fn in contract.functions:
        evidence.append(
            Evidence(
                evidence_id=f"E-MODEL-{fn.name}",
                kind="model",
                claim=f"Function {fn.name} has modifiers={list(fn.modifiers)} and writes={list(fn.writes)}.",
                source=contract.source,
                location=f"line {fn.line}",
            )
        )
    return tuple(evidence)
