            runtime_requirements=_runtime_requirements(contract, fn),
            execution_requirements=(
                *_execution_requirements(contract, fn),
                *_execution_dataflow_requirements(contract, fn, semantic_evidence, frozenset()),
            ),
            state_setup_candidates=(
                *_state_setup_candidates(contract, fn, constraints, semantic_evidence),
                *_internal_state_setup_candidates(contract, fn, semantic_evidence),
            ),
        )

    def required_state_names(fn: FunctionModel) -> tuple[str, ...]:
        names = list(_state_names_from_predicates(fn))
        for constraint in constraints:
            if constraint.function != fn.name or ".length" not in constraint.predicate:
                continue
            match = re.search(r"\b([A-Za-z_]\w*)\.length\b", constraint.predicate)
            if match and match.group(1) not in names:
                names.append(match.group(1))

        # Execution-readiness dependencies can introduce state that is not
        # mentioned in the consumer's own state-predicate list. For example,
        # a positive maxWithdraw(msg.sender) path requires the caller to own
        # shares. Feed those discovered state dependencies into the same
        # recursive writer solver used for ordinary state predicates.
        for state in _state_names_from_internal_predicates(contract, fn):
            if state not in names:
                names.append(state)
        readiness = planner_readiness(fn)
        for requirement in readiness.execution_requirements:
            if requirement.kind != "caller_state_dependency" or requirement.status != "discovered":
                continue
            match = re.search(r"\bbalanceOf\s*\(", requirement.subject)
            if match and "balanceOf" not in names:
                names.append("balanceOf")
        return tuple(names)

    def visit(fn: FunctionModel, stack: tuple[str, ...], depth: int) -> tuple[SetupAction, ...] | None:
        key = (fn.name, stack)
        if key in memo:
            return memo[key]
        if depth > max_depth or fn.name in stack:
            memo[key] = None
            return None
        readiness = planner_readiness(fn)

        # A state-observation prerequisite is not itself a reason to abandon
        # planning when the target model already exposes a writer for that
        # exact state. The writer must still pass its own readiness checks below;
        # this is the boundary between "state is currently unknown" and "state
        # can be established by a verified target transition". Other unresolved
        # prerequisites remain hard blockers, and state with no writer remains
        # unresolved.
        planned_state_names = set(required_state_names(fn))