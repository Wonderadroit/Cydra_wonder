from cydra.hypothesis_selection import select_next_hypothesis
from cydra.models import Experiment, Hypothesis, Invariant

def main():
    inv_a=Invariant("INV-A","a","benchmark-048",0.9)
    inv_b=Invariant("INV-B","b","benchmark-048",0.8)
    h_a=Hypothesis("H-A","a","INV-A","a","caller","impact")
    h_b=Hypothesis("H-B","b","INV-B","b","caller","impact")
    e_a=Experiment("E-A","H-A","a",("one",),1.0)
    e_b=Experiment("E-B","H-B","b",("one",),1.0)
    selected=select_next_hypothesis((h_a,h_b),(inv_a,inv_b),(e_a,e_b),observed_statuses={"H-A":"UNMEASURABLE"})
    assert selected.hypothesis.hypothesis_id=="H-B"
    try:
        select_next_hypothesis((h_a,),(inv_a,),(e_a,),observed_statuses={"H-A":"UNMEASURABLE"})
    except ValueError as exc:
        assert "no non-excluded hypothesis" in str(exc)
    else:
        raise AssertionError("unmeasurable-only candidate must be exhausted")
    print("Benchmark 048: PASS")
    print("unmeasurable_alternate_candidate=selected")
    print("unmeasurable_only_candidate=exhausted")

if __name__=="__main__":
    main()
