import pytest
from backend.models.debate import AgentVote, DebateResult
from backend.agents.consensus import evaluate_consensus

def test_consensus_unanimous_agreement():
    proposal_id = "prop-xyz"
    votes = [
        AgentVote(agent_name="StrategySynthesizer", vote="AGREE", confidence=0.9, reasoning="Strong thesis"),
        AgentVote(agent_name="DevilsAdvocate", vote="AGREE", confidence=0.8, reasoning="Acceptable risks"),
        AgentVote(agent_name="MarketIntel", vote="AGREE", confidence=0.85, reasoning="Regime aligned"),
    ]
    weights = {"StrategySynthesizer": 0.4, "DevilsAdvocate": 0.4, "MarketIntel": 0.2}

    result = evaluate_consensus(proposal_id, votes, weights)
    assert result.consensus_reached is True
    assert result.winning_proposal_id == proposal_id
    assert result.consensus_score > 0.33
    assert "Reached" in result.summary

def test_consensus_rejection_on_strong_disagreement():
    proposal_id = "prop-xyz"
    votes = [
        AgentVote(agent_name="StrategySynthesizer", vote="AGREE", confidence=0.7, reasoning="Good"),
        AgentVote(agent_name="DevilsAdvocate", vote="DISAGREE", confidence=0.9, reasoning="Earnings risk tail event"),
        AgentVote(agent_name="MarketIntel", vote="DISAGREE", confidence=0.8, reasoning="Trend bearish"),
    ]
    weights = {"StrategySynthesizer": 0.4, "DevilsAdvocate": 0.4, "MarketIntel": 0.2}

    result = evaluate_consensus(proposal_id, votes, weights)
    assert result.consensus_reached is False
    assert result.winning_proposal_id is None
    assert result.consensus_score < 0.33
    assert "Failed" in result.summary

def test_consensus_threshold_boundary():
    # Test right around 0.33 threshold
    proposal_id = "prop-border"
    # Strategy: 0.4 * 0.9 = 0.36
    # MarketIntel: 0.2 * 0.8 = 0.16
    # DevilsAdvocate: 0.4 * (-0.4) = -0.16
    # Total = 0.36 / 1.0 = 0.36 >= 0.33 -> Passed
    votes = [
        AgentVote(agent_name="StrategySynthesizer", vote="AGREE", confidence=0.9, reasoning="Yes"),
        AgentVote(agent_name="MarketIntel", vote="AGREE", confidence=0.8, reasoning="Yes"),
        AgentVote(agent_name="DevilsAdvocate", vote="DISAGREE", confidence=0.4, reasoning="Minor concern"),
    ]
    weights = {"StrategySynthesizer": 0.4, "DevilsAdvocate": 0.4, "MarketIntel": 0.2}

    result = evaluate_consensus(proposal_id, votes, weights)
    assert result.consensus_reached is True
    assert pytest.approx(result.consensus_score, 0.01) == 0.36
