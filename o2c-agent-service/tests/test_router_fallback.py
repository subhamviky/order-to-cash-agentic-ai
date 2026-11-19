"""The router's degraded answer names its reason (aidlc-change, hub design note AD-01)."""
import json

from o2c_agent_service.agents.router_agent import RouterAgent


def test_an_unclassified_request_names_its_reason():
    state = {}
    answer = RouterAgent()._fallback(state, None)
    assert state['intent'] == 'UNSUPPORTED'
    assert answer['degraded'] and answer['reason'] == 'UNCLASSIFIED'
    assert json.loads(answer['text']) == {'intent': 'UNSUPPORTED', 'reason': 'UNCLASSIFIED'}
