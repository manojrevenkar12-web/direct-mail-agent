import numpy as np
from scipy.stats import ks_2samp

from mailagent import mailfile, rules
from mailagent.optimise import assign_cells, cell_edges, cell_name
from mailagent.schema import CellPlan, Creative, Plan
from mailworld.market import Market


def setup(n=20_000, letters=300, hold=33):
    m = Market("dev", size=n)
    uni = m.universe("2026-01-17")
    resp, val, _ = m.scores(uni["company_id"], "2026-01-17")
    mask = rules.evaluate(uni)
    edges, vedge = cell_edges(resp, val, mask == 0)
    codes = assign_cells(resp, val, edges, vedge)
    cells = [
        CellPlan(
            cell=cell_name(c),
            available=int(((mask == 0) & (codes == c)).sum()),
            letters=300,
            holdout=33,
            value_per_letter=1.0,
            p_profitable=0.5,
            sampled_net=0.1,
        )
        for c in np.unique(codes)
    ]
    plan = Plan(
        round=1,
        drop_date="2026-01-26",
        budget=110000,
        letters=300 * len(cells),
        holdout=33 * len(cells),
        cost=0.55 * letters * len(cells),
        holdout_share=0.1,
        cells=cells,
        creative_shares={"FLEXI-A": 0.5, "FLEXI-B": 0.5},
        excluded_sectors=[],
        model_version="v6",
        band_edges=edges,
        value_edge=vedge,
        expected_incremental_value=0,
    )
    creatives = [
        Creative(code=c, product="flexi_loan", approved=True, approved_until="2027-12-31")
        for c in ("FLEXI-A", "FLEXI-B")
    ]
    return m, uni, resp, val, mask, plan, creatives


def test_same_plan_same_file():
    _, uni, resp, val, mask, plan, _ = setup()
    a = mailfile.build(plan, uni, resp, val, mask)
    b = mailfile.build(plan, uni, resp, val, mask)
    assert a.sha256 == b.sha256 and a.letters == 300 * len(plan.cells)


def test_holdout_is_a_fair_comparison():
    m, uni, resp, val, mask, plan, _ = setup(200_000, letters=9000, hold=1000)
    f = mailfile.build(plan, uni, resp, val, mask)
    rows = f.company_id - m.company_id[0]
    for c in np.unique(f.cell):
        sel = f.cell == c
        a, h = resp[rows[sel & (f.arm == 1)]], resp[rows[sel & (f.arm == 0)]]
        assert ks_2samp(a, h).pvalue > 0.001  # same score distribution in both arms


def test_checks_pass_then_catch_each_problem():
    m, uni, resp, val, mask, plan, creatives = setup()
    f = mailfile.build(plan, uni, resp, val, mask)
    assert all(c.passed for c in mailfile.check(f, plan, uni, creatives, budget_cap=150000))
    # someone objects after the file was built
    first = f.company_id[f.arm == 1][0] - m.company_id[0]
    uni2 = {**uni, "objected": uni["objected"].copy()}
    uni2["objected"][first] = True
    failed = {c.check for c in mailfile.check(f, plan, uni2, creatives, budget_cap=150000) if not c.passed}
    assert failed == {"suppressions"}
    # the creative's approval expires before the drop
    late = [creatives[0].model_copy(update={"approved_until": "2026-01-20"}), creatives[1]]
    failed = {c.check for c in mailfile.check(f, plan, uni, late, budget_cap=150000) if not c.passed}
    assert failed == {"creatives_approved"}
    # a budget above the cap
    over = plan.model_copy(update={"budget": 200000})
    failed = {c.check for c in mailfile.check(f, over, uni, creatives, budget_cap=150000) if not c.passed}
    assert "budget" in failed


def test_a_changed_file_has_a_different_hash():
    _, uni, resp, val, mask, plan, _ = setup()
    f = mailfile.build(plan, uni, resp, val, mask)
    sha = f.sha256
    f.arm[0] = 1 - f.arm[0]
    assert f.sha256 != sha
