from types import SimpleNamespace

from fastapi.testclient import TestClient

from mailagent import settings
from mailagent.api import create_app
from mailagent.claude import ClaudeReader
from mailagent.schema import Message


def test_approval_api(make_agent, world, conn):
    agent, truth = make_agent()
    for m, t in world.inbox_for(1):
        truth[m.id] = t
    out = agent.plan_round(1)
    rounds = {
        1: {
            "plan": out.plan.model_dump(),
            "sha256": out.file.sha256,
            "approval_id": out.approval_id,
            "brief": out.brief,
            "checks": [c.model_dump() for c in out.checks],
        }
    }
    app = TestClient(create_app(conn, rounds, clock=lambda: settings.iso(settings.plan_date(1))))
    assert app.get("/rounds").json()[0]["status"] == "awaiting_approval"
    body = {"approve": True, "sha256": out.file.sha256}
    assert (
        app.post("/rounds/1/decision", json=body, headers={"X-User": "jo", "X-Role": "sales_lead"}).status_code == 403
    )
    stale = {**body, "sha256": "0" * 64}
    assert (
        app.post(
            "/rounds/1/decision", json=stale, headers={"X-User": "sam", "X-Role": "head_of_direct_acquisition"}
        ).status_code
        == 409
    )
    r = app.post("/rounds/1/decision", json=body, headers={"X-User": "sam", "X-Role": "head_of_direct_acquisition"})
    assert r.json()["status"] == "approved"
    assert app.get("/ledger").json()["intact"]


class FakeClient:
    def __init__(self, payload):
        self.payload, self.sent = payload, None
        self.messages = self

    def create(self, **kw):
        self.sent = kw
        block = SimpleNamespace(type="tool_use", input=self.payload)
        usage = SimpleNamespace(input_tokens=1200, output_tokens=80, cache_read_input_tokens=1800)
        return SimpleNamespace(content=[block], usage=usage)


def test_claude_adapter_forces_the_tool_and_caches_the_prompt():
    client = FakeClient(
        {
            "directives": [
                {
                    "message_id": "m1",
                    "kind": "set_budget",
                    "value": 95000,
                    "quote": "Please plan the round at £95,000 in total.",
                }
            ],
            "routes": [],
        }
    )
    reader = ClaudeReader(client=client, model="claude-sonnet-4-5")
    msg = Message(
        id="m1",
        received="2026-01-10",
        sender="a",
        sender_role="head_of_direct_acquisition",
        authenticated=True,
        subject="s",
        body="Please plan the round at £95,000 in total.",
    )
    reading, usage = reader.read_inbox([msg], {"round": 1})
    assert reading.directives[0].value == 95000 and usage.cache_read_tokens == 1800
    assert client.sent["tool_choice"] == {"type": "tool", "name": "record_inbox"}
    assert client.sent["system"][0]["cache_control"] == {"type": "ephemeral"}
