from typing import List
from backend.models.debate import AgentVote, DebateResult

def evaluate_consensus(proposal_id: str, votes: List[AgentVote], weights: dict) -> DebateResult:
    """
    Deterministic weighted voting system. No LLM.
    Weights example: {"StrategySynthesizer": 0.4, "DevilsAdvocate": 0.3, "MarketIntel": 0.3}
    """
    total_score = 0.0
    total_weight = 0.0
    
    for v in votes:
        weight = weights.get(v.agent_name, 0.0)
        total_weight += weight
        
        # AGREE = positive confidence, DISAGREE = negative confidence
        multiplier = 1.0 if v.vote.upper() == "AGREE" else -1.0
        score_contribution = (v.confidence * multiplier) * weight
        total_score += score_contribution
        
    # Normalize score to -1.0 to 1.0 range based on total weight
    if total_weight > 0:
        normalized_score = total_score / total_weight
    else:
        normalized_score = -1.0
        
    # Threshold for approval is a score >= 0.33 (meaning mild consensus to agree)
    # 0.66 would be strong consensus
    is_approved = normalized_score >= 0.33
    
    summary = f"Consensus {'Reached' if is_approved else 'Failed'} with score {normalized_score:.2f}."
    
    return DebateResult(
        proposal_id=proposal_id,
        votes=votes,
        consensus_reached=is_approved,
        consensus_score=normalized_score,
        winning_proposal_id=proposal_id if is_approved else None,
        summary=summary
    )
