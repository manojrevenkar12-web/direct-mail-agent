import pytest

from agentrt.approvals import ApprovalError, Approvals, Person
from agentrt.ledger import Ledger
from agentrt.memory import Memory, MemoryRuleError
from agentrt.tasks import PersonTasks, Steps
from agentrt.tools import PermissionDenied, Policy, Tool, Toolbox


def test_ledger_chain_detects_tampering(conn):
    led = Ledger(conn)
    for i in range(5):
        led.record(at="2026-01-01", run="r", step="s", actor="a", kind="k", decision={"i": i}, reason="because")
    assert led.verify() == (True, None)
    conn.execute("update decisions set decision = '{\"i\":99}' where seq = 3")
    assert led.verify() == (False, 3)


def test_ledger_needs_a_reason(conn):
    with pytest.raises(ValueError):
        Ledger(conn).record(at="x", run="r", step="s", actor="a", kind="k", decision={}, reason=" ")


def test_memory_versions_and_rules(conn):
    m = Memory(conn)
    m.put("facts/x", 1, provenance="results", run="r1", at="d")
    m.put("facts/x", 2, provenance="results", run="r2", at="d")
    assert m.get("facts/x") == 2 and [h["value"] for h in m.history("facts/x")] == [1, 2]
    with pytest.raises(MemoryRuleError):
        m.put("facts/x", 3, provenance="agent_note", run="r3", at="d")  # the model cannot write a fact
    m.put("notes/x", "looks seasonal", provenance="agent_note", run="r3", at="d")
    assert "notes/x" not in m.facts()


def test_steps_resume_without_rerunning(conn):
    steps, calls = Steps(conn), []
    steps.run("r", "a", lambda: calls.append("a") or {"v": 1})
    with pytest.raises(RuntimeError):
        steps.run("r", "b", lambda: (_ for _ in ()).throw(RuntimeError("crash")))
    assert steps.status("r") == {"a": "done", "b": "started"}
    assert steps.run("r", "a", lambda: calls.append("a again")) == {"v": 1}
    assert steps.run("r", "b", lambda: calls.append("b") or 2) == 2
    assert calls == ["a", "b"]


def test_person_tasks_deduplicate(conn):
    t = PersonTasks(conn)
    a = t.open(run="r", owner_role="ops", kind="k", payload={}, dedupe="x")
    b = t.open(run="r", owner_role="ops", kind="k", payload={}, dedupe="x")
    assert a == b and len(t.list()) == 1


def test_toolbox_permissions_and_idempotent_effects(conn):
    led = Ledger(conn)
    box = Toolbox(conn, Policy({"agent": {"read"}, "code": {"read", "send"}}), led, lambda: "d")
    sent = []
    box.register(Tool("send", "send", lambda x: sent.append(x) or {"ok": x}, effect=True))
    with pytest.raises(PermissionDenied):
        box.call(role="agent", run="r", name="send", idempotency_key="k", x=1)
    assert box.call(role="code", run="r", name="send", idempotency_key="k", x=1) == {"ok": 1}
    assert box.call(role="code", run="r", name="send", idempotency_key="k", x=1) == {"ok": 1}
    assert sent == [1]
    assert [e["kind"] for e in led.entries()] == ["denied", "effect"]
    with pytest.raises(ValueError):
        box.call(role="code", run="r", name="send", x=2)  # effects need a key


def test_approvals_are_bound_to_the_artefact_and_the_role(conn):
    ap = Approvals(conn, Ledger(conn))
    i = ap.request(
        run="r",
        kind="mail_file",
        artefact_sha="aaa",
        needs_role="head",
        requested_by="agent",
        expires_at="2026-01-10",
        at="2026-01-01",
    )
    with pytest.raises(ApprovalError):
        ap.decide(i, person=Person("bot", "agent"), approve=True, at="2026-01-02")
    with pytest.raises(ApprovalError):
        ap.decide(i, person=Person("pat", "sales_lead"), approve=True, at="2026-01-02")
    with pytest.raises(ApprovalError):
        ap.decide(i, person=Person("sam", "head"), approve=True, at="2026-01-11")
    ap.decide(i, person=Person("sam", "head"), approve=True, at="2026-01-02")
    assert ap.valid(kind="mail_file", artefact_sha="aaa", at="2026-01-05")
    assert not ap.valid(kind="mail_file", artefact_sha="aab", at="2026-01-05")
    assert not ap.valid(kind="mail_file", artefact_sha="aaa", at="2026-01-11")
    with pytest.raises(ApprovalError):
        ap.decide(i, person=Person("sam", "head"), approve=False, at="2026-01-03")
