"""
Copilot Routes
==============
HTTP endpoints for the PulseOS AI Copilot.

All endpoints are POST to avoid long URLs for rich context payloads.

Endpoints
---------
POST /copilot/chat
    General-purpose copilot chat with optional context objects.

POST /copilot/summarize
    Network health summary grounded in current backend state.

POST /copilot/explain/scenario
    Plain-language explanation of a simulated scenario.

POST /copilot/explain/recommendation
    Why a specific recommendation was generated and what it achieves.

POST /copilot/explain/optimization
    Plain-language summary of a QUBO solver run.

POST /copilot/answer
    Free-form operator question answered against all available context.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ai.copilot import Copilot
from schemas.dashboard import DashboardSummary
from schemas.network import NetworkState
from schemas.optimization import OptimizationResult
from schemas.prediction import PredictionResult
from schemas.recommendation import Recommendation
from schemas.scenario import Scenario
from services.deps import get_copilot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["AI Copilot"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CopilotChatRequest(BaseModel):
    """General-purpose copilot chat request."""

    message: str = Field(
        ..., min_length=1, max_length=2000,
        description="The operator's question or command",
    )
    network_state: Optional[NetworkState] = Field(
        None, description="Current network topology snapshot (optional)"
    )
    scenario: Optional[Scenario] = Field(
        None, description="Active simulation scenario (optional)"
    )
    predictions: Optional[List[PredictionResult]] = Field(
        None, description="Congestion forecast results (optional)"
    )
    optimization: Optional[OptimizationResult] = Field(
        None, description="Most recent QUBO solver result (optional)"
    )
    recommendation: Optional[Recommendation] = Field(
        None, description="A specific recommendation to discuss (optional)"
    )
    dashboard: Optional[DashboardSummary] = Field(
        None, description="Aggregated dashboard KPI snapshot (optional)"
    )


class CopilotSummarizeRequest(BaseModel):
    """Request for a network health summary."""

    network_state: Optional[NetworkState] = None
    dashboard: Optional[DashboardSummary] = None
    predictions: Optional[List[PredictionResult]] = None


class CopilotScenarioRequest(BaseModel):
    """Request to explain an active scenario."""

    scenario: Scenario = Field(..., description="The scenario to explain")
    network_state: Optional[NetworkState] = None


class CopilotRecommendationRequest(BaseModel):
    """Request to explain a specific recommendation."""

    recommendation: Recommendation = Field(
        ..., description="The recommendation to explain"
    )
    network_state: Optional[NetworkState] = None
    prediction: Optional[PredictionResult] = Field(
        None, description="The prediction that triggered the recommendation"
    )


class CopilotOptimizationRequest(BaseModel):
    """Request to explain an optimization result."""

    result: OptimizationResult = Field(
        ..., description="The optimization result to explain"
    )
    network_state: Optional[NetworkState] = None


class CopilotAnswerRequest(BaseModel):
    """Free-form question against all available context."""

    question: str = Field(
        ..., min_length=1, max_length=2000,
        description="The operator's question",
    )
    network_state: Optional[NetworkState] = None
    scenario: Optional[Scenario] = None
    predictions: Optional[List[PredictionResult]] = None
    optimization: Optional[OptimizationResult] = None
    recommendation: Optional[Recommendation] = None
    dashboard: Optional[DashboardSummary] = None


class CopilotResponse(BaseModel):
    """Standard copilot response envelope."""

    reply: str = Field(..., description="The copilot's natural-language response")
    method: str = Field(..., description="The copilot method that produced this response")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=CopilotResponse)
def chat(
    body: CopilotChatRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    General-purpose copilot chat endpoint.

    Supply any combination of context objects alongside the message.
    The copilot grounds its answer in the provided data and maintains
    conversation history within this request's session.
    """
    logger.info("POST /copilot/chat | message_len=%d", len(body.message))
    reply = copilot.chat(
        message=body.message,
        network_state=body.network_state,
        scenario=body.scenario,
        predictions=body.predictions,
        optimization=body.optimization,
        recommendation=body.recommendation,
        dashboard=body.dashboard,
    )
    return CopilotResponse(reply=reply, method="chat")


@router.post("/summarize", response_model=CopilotResponse)
def summarize(
    body: CopilotSummarizeRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    Generate a concise network health summary grounded in current backend state.

    Returns a 3-6 sentence plain-language summary covering tower status,
    congestion outlook, and QoS/QoE if available.
    """
    logger.info("POST /copilot/summarize")
    reply = copilot.summarize_network(
        network_state=body.network_state,
        dashboard=body.dashboard,
        predictions=body.predictions,
    )
    return CopilotResponse(reply=reply, method="summarize_network")


@router.post("/explain/scenario", response_model=CopilotResponse)
def explain_scenario(
    body: CopilotScenarioRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    Explain an active simulation scenario in plain language.

    Describes the event type, affected towers, computed effects, and
    the operational risks the operator should be aware of.
    """
    logger.info(
        "POST /copilot/explain/scenario | scenario_id=%s",
        body.scenario.id,
    )
    reply = copilot.explain_scenario(
        scenario=body.scenario,
        network_state=body.network_state,
    )
    return CopilotResponse(reply=reply, method="explain_scenario")


@router.post("/explain/recommendation", response_model=CopilotResponse)
def explain_recommendation(
    body: CopilotRecommendationRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    Explain why a recommendation was generated and what it will achieve.

    Provides action rationale, supporting data, expected outcome, and
    any caveats the operator should consider.
    """
    logger.info(
        "POST /copilot/explain/recommendation | rec_id=%s",
        body.recommendation.id,
    )
    reply = copilot.explain_recommendation(
        recommendation=body.recommendation,
        network_state=body.network_state,
        prediction=body.prediction,
    )
    return CopilotResponse(reply=reply, method="explain_recommendation")


@router.post("/explain/optimization", response_model=CopilotResponse)
def explain_optimization(
    body: CopilotOptimizationRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    Explain a QUBO optimization run in plain language.

    Translates solver-level output (energy, variable assignments) into
    operational meaning for the network operator.
    """
    logger.info(
        "POST /copilot/explain/optimization | run_id=%s",
        body.result.run_id,
    )
    reply = copilot.explain_optimization(
        result=body.result,
        network_state=body.network_state,
    )
    return CopilotResponse(reply=reply, method="explain_optimization")


@router.post("/answer", response_model=CopilotResponse)
def answer(
    body: CopilotAnswerRequest,
    copilot: Copilot = Depends(get_copilot),
) -> CopilotResponse:
    """
    Answer a free-form operator question grounded in all available context.

    The most flexible endpoint: provide any combination of context objects
    alongside the question and the copilot will draw only on what is present.
    """
    logger.info("POST /copilot/answer | question_len=%d", len(body.question))
    reply = copilot.answer_question(
        question=body.question,
        network_state=body.network_state,
        scenario=body.scenario,
        predictions=body.predictions,
        optimization=body.optimization,
        recommendation=body.recommendation,
        dashboard=body.dashboard,
    )
    return CopilotResponse(reply=reply, method="answer_question")
