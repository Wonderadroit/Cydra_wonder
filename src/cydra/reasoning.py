from __future__ import annotations

from .models import Evidence, Experiment, Hypothesis, Invariant, ContractModel


def access_control_invariant(contract: ContractModel, privileged_modifier: str = "onlyGov") -> Invariant:
    return Invariant("INV-AUTH-001", f"Administrative state-changing operations must enforce {privileged_modifier} authorization.", "structural sibling-function rule; modifier-bearing administrative functions", 0.90)


def generate_access_control_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    admin_functions = [f for f in contract.functions if f.name.startswith(("set", "add", "remove", "update", "accept"))]
    protected = [f for f in admin_functions if f.modifiers]
    if not protected:
        return ()
    invariant = access_control_invariant(contract)
    return tuple(Hypothesis(f"H-AUTH-{fn.name}", f"{fn.name} may permit an unauthorized caller to mutate privileged state.", invariant.invariant_id, fn.name, "arbitrary external caller", "privileged configuration or authorization state can be changed", evidence_ids=(f"E-MODEL-{fn.name}",)) for fn in admin_functions if not fn.modifiers)


def initialization_invariant(contract: ContractModel) -> Invariant:
    return Invariant("INV-INIT-001", "Initialization must not allow an arbitrary caller to claim privileged initialization state after deployment.", "lifecycle rule; initializer function and privileged state assignment", 0.90)


def generate_initialization_hypotheses(contract: ContractModel) -> tuple[Hypothesis, ...]:
    initializers = [f for f in contract.functions if f.name in {"initialize", "init"} and f.visibility in {"public", "external"}]
    if not initializers:
        return ()
    invariant = initialization_invariant(contract)
    return tuple(Hypothesis(f"H-INIT-{fn.name}", f"{fn.name} may be callable in the deployed uninitialized state by an arbitrary caller, allowing privileged initialization state to be claimed.", invariant.invariant_id, fn.name, "arbitrary external caller", "attacker-controlled initialization or privileged state", evidence_ids=(f"E-MODEL-{fn.name}",)) for fn in initializers)


def plan_access_control_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(f"X-{hypothesis.hypothesis_id}", hypothesis.hypothesis_id, f"Execute {hypothesis.target_function} from an unprivileged actor and assert that the privileged state does not change; then repeat against the patched version.", ("missing authorization is exploitable", "authorization is enforced elsewhere"), 1.0)


def plan_initialization_experiment(hypothesis: Hypothesis) -> Experiment:
    return Experiment(f"X-{hypothesis.hypothesis_id}", hypothesis.hypothesis_id, f"Deploy the target, call {hypothesis.target_function} as an arbitrary actor, and assert the actor cannot claim privileged initialization state; repeat against the patched version.", ("deployed lifecycle state is takeover-capable", "initializer is unavailable or safely initialized"), 1.0)


def build_evidence(contract: ContractModel, hypotheses: tuple[Hypothesis, ...]) -> tuple[Evidence, ...]:
    return tuple(Evidence(f"E-MODEL-{fn.name}", "model", f"Function {fn.name} has modifiers={list(fn.modifiers)} and writes={list(fn.writes)}.", contract.source, f"line {fn.line}") for fn in contract.functions)
