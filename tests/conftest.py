import pytest

from agentrt.store import connect
from mailworld.adapters import World, ports
from mailworld.llm import SimulatedReader
from mailworld.market import Market

SMALL = 30_000


@pytest.fixture
def conn():
    return connect()


@pytest.fixture
def world():
    return World(Market("dev", size=SMALL))


@pytest.fixture
def make_agent(conn, world):
    from mailagent.agent import Mode, RoundAgent

    def make(mode=None, reader="sim", truth=None):
        truth = truth if truth is not None else {}
        rd = SimulatedReader(truth, set(), seed=3) if reader == "sim" else reader
        agent = RoundAgent(conn, reader=rd, mode=mode or Mode(), **ports(world))
        return agent, truth

    return make
