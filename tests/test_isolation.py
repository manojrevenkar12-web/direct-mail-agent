"""The agent never sees the truth: nothing the agent runs imports the simulated market or the evaluation."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def imports(pkg: str) -> set[str]:
    out = set()
    for f in (SRC / pkg).rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Import):
                out |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                out.add(node.module.split(".")[0])
    return out


def test_agent_and_runtime_never_import_the_world():
    for pkg in ("agentrt", "mailagent"):
        assert not imports(pkg) & {"mailworld", "mail_eval"}, pkg


def test_runtime_knows_nothing_about_mail():
    assert "mailagent" not in imports("agentrt")


def test_model_context_has_no_company(make_agent, world):
    agent, _ = make_agent()
    ctx = agent.context(1)
    text = repr(ctx)
    ids = world.m.company_id
    assert str(ids[0]) not in text and str(ids[-1]) not in text
    assert set(ctx) == {"round", "drop_date", "default_budget", "hard_budget_cap", "sectors", "creatives", "last_round"}
