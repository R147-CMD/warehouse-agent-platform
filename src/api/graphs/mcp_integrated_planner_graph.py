# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
MCP-Enabled Warehouse Operational Assistant - Planner/Router Graph
Integrates MCP framework with main agent workflow for dynamic tool discovery and execution.

This module implements the MCP-enhanced planner/router agent that:
1. Analyzes user intents using MCP-based classification
2. Routes to appropriate MCP-enabled specialized agents
3. Coordinates multi-agent workflows with dynamic tool binding
4. Synthesizes responses from multiple agents with MCP tool results
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict, Annotated, Any
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
from dataclasses import asdict
import inspect
import logging
import asyncio
import threading

from src.api.services.mcp.tool_discovery import ToolDiscoveryService
from src.api.services.mcp.tool_binding import ToolBindingService
from src.api.services.mcp.tool_routing import ToolRoutingService, RoutingStrategy
from src.api.services.mcp.tool_validation import ToolValidationService
from src.api.services.mcp.base import MCPManager
from src.api.services.approval import (
    ApprovalDecision,
    ApprovalExecutionContext,
    ApprovalInterruptPayload,
    ApprovalRecord,
    ApprovalResumePayload,
    bind_approval_context,
)
from src.api.services.checkpointing import get_checkpoint_manager
from src.api.services.reasoning.reflection_loop import (
    DEFAULT_MAX_REFLECTION_ITERATIONS,
    build_planner_decision,
    review_agent_outcome_with_judge,
)
from src.api.services.reasoning.evidence_join import (
    build_collaboration_plan,
    join_agent_evidence,
    summarize_agent_evidence,
)
from src.api.services.runs import (
    RunCancelled,
    RunEventSeverity,
    RunEventType,
    RunExecutionContext,
    RunUpdate,
    bind_run_context,
    get_run_context,
    get_run_manager,
)
from src.api.utils.log_utils import sanitize_log_data

logger = logging.getLogger(__name__)


# Constants for agent timeouts
AGENT_INIT_TIMEOUT = 5.0  # 5 seconds for agent initialization
AGENT_TIMEOUT_REASONING = 90.0  # 90s for reasoning queries
AGENT_TIMEOUT_COMPLEX = 50.0  # 50s for complex queries
AGENT_TIMEOUT_SIMPLE = 45.0  # 45s for simple queries

# Constants for complex query detection
COMPLEX_QUERY_KEYWORDS = [
    "optimize", "optimization", "optimizing", "analyze", "analysis", "analyzing",
    "relationship", "between", "compare", "evaluate", "correlation", "impact",
    "effect", "factors", "consider", "considering", "recommend", "recommendation",
    "strategy", "strategies", "improve", "improvement", "best practices"
]

COMPLEX_QUERY_ACTIONS = ["create", "dispatch", "assign", "show", "list", "get", "check"]
COMPLEX_QUERY_WORD_COUNT_THRESHOLD = 15
CHECKPOINT_NAMESPACE = "warehouse_mcp_planner"


class _ApprovalWorkflowError(RuntimeError):
    """Raised when persisted approval workflow data cannot be trusted."""


_SENSITIVE_CONTEXT_KEYS = {
    "authorization",
    "bearer",
    "bearer_token",
    "access_token",
    "refresh_token",
    "token",
    "user",
    "current_user",
}


def _sanitize_graph_context(value: Any) -> Any:
    """Copy caller context without credentials or complete user objects."""
    if isinstance(value, dict):
        return {
            key: _sanitize_graph_context(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_CONTEXT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_graph_context(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_graph_context(item) for item in value)
    return value


def _extract_message_text(state: "MCPWarehouseState") -> Optional[str]:
    """Helper to extract text content from the latest message in state."""
    if not state.get("messages"):
        return None
    
    latest_message = state["messages"][-1]
    if isinstance(latest_message, HumanMessage):
        return latest_message.content
    return str(latest_message.content)


def _detect_complex_query(message_text: str) -> bool:
    """Helper to detect if a query is complex and needs more processing time."""
    message_lower = message_text.lower()
    return (
        any(keyword in message_lower for keyword in COMPLEX_QUERY_KEYWORDS) or
        (message_lower.count(" and ") > 0 and any(action in message_lower for action in COMPLEX_QUERY_ACTIONS)) or
        len(message_text.split()) > COMPLEX_QUERY_WORD_COUNT_THRESHOLD
    )


def _calculate_agent_timeout(enable_reasoning: bool, is_complex_query: bool) -> float:
    """Helper to calculate agent timeout based on query characteristics."""
    if enable_reasoning:
        return AGENT_TIMEOUT_REASONING
    elif is_complex_query:
        return AGENT_TIMEOUT_COMPLEX
    return AGENT_TIMEOUT_SIMPLE


def _convert_response_to_dict(response: Any, default_response_type: str) -> Dict[str, Any]:
    """Helper to convert agent response (dict or object) to standardized dict format."""
    if isinstance(response, dict):
        return response
    
    # Convert response object to dict
    return {
        "natural_language": response.natural_language if hasattr(response, "natural_language") else str(response),
        "data": response.data if hasattr(response, "data") else {},
        "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
        "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
        "response_type": response.response_type if hasattr(response, "response_type") else default_response_type,
        "mcp_tools_used": response.mcp_tools_used or [] if hasattr(response, "mcp_tools_used") else [],
        "tool_execution_results": response.tool_execution_results or {} if hasattr(response, "tool_execution_results") else {},
        "actions_taken": response.actions_taken or [] if hasattr(response, "actions_taken") else [],
        "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
        "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
    }


def _create_error_response(agent_name: str, message_text: str, error: Exception, is_timeout: bool = False) -> Dict[str, Any]:
    """Helper to create standardized error response for agents."""
    if is_timeout:
        return {
            "natural_language": f"I received your {agent_name} query: '{message_text}'. The system is taking longer than expected to process it. Please try again or rephrase your question.",
            "data": {"error": "timeout", "message": str(error)},
            "recommendations": [],
            "confidence": 0.3,
            "response_type": "timeout",
            "mcp_tools_used": [],
            "tool_execution_results": {},
        }
    return {
        "natural_language": f"I received your {agent_name} query: '{message_text}'. However, I encountered an error processing it: {str(error)[:100]}. Please try rephrasing your question.",
        "data": {"error": str(error)[:200]},
        "recommendations": [],
        "confidence": 0.3,
        "response_type": "error",
        "mcp_tools_used": [],
        "tool_execution_results": {},
    }


def _convert_reasoning_chain_to_dict(reasoning_chain: Any) -> Optional[Dict[str, Any]]:
    """Helper to convert ReasoningChain dataclass to dict, avoiding recursion."""
    from dataclasses import is_dataclass
    
    if not is_dataclass(reasoning_chain):
        return reasoning_chain if isinstance(reasoning_chain, dict) else None
    
    try:
        reasoning_chain_dict = {
            "chain_id": getattr(reasoning_chain, "chain_id", ""),
            "query": getattr(reasoning_chain, "query", ""),
            "reasoning_type": getattr(reasoning_chain, "reasoning_type", ""),
            "final_conclusion": getattr(reasoning_chain, "final_conclusion", ""),
            "overall_confidence": float(getattr(reasoning_chain, "overall_confidence", 0.0)),
            "execution_time": float(getattr(reasoning_chain, "execution_time", 0.0)),
        }
        
        # Convert enum to string
        if hasattr(reasoning_chain_dict["reasoning_type"], "value"):
            reasoning_chain_dict["reasoning_type"] = reasoning_chain_dict["reasoning_type"].value
        
        # Convert datetime
        if hasattr(reasoning_chain, "created_at"):
            created_at = getattr(reasoning_chain, "created_at")
            if hasattr(created_at, "isoformat"):
                reasoning_chain_dict["created_at"] = created_at.isoformat()
            else:
                reasoning_chain_dict["created_at"] = str(created_at)
        
        # Convert steps
        if hasattr(reasoning_chain, "steps") and reasoning_chain.steps:
            converted_steps = []
            for step in reasoning_chain.steps:
                if is_dataclass(step):
                    step_dict = {
                        "step_id": getattr(step, "step_id", ""),
                        "step_type": getattr(step, "step_type", ""),
                        "description": getattr(step, "description", ""),
                        "reasoning": getattr(step, "reasoning", ""),
                        "confidence": float(getattr(step, "confidence", 0.0)),
                    }
                    if hasattr(step, "timestamp"):
                        timestamp = getattr(step, "timestamp")
                        if hasattr(timestamp, "isoformat"):
                            step_dict["timestamp"] = timestamp.isoformat()
                        else:
                            step_dict["timestamp"] = str(timestamp)
                    step_dict["input_data"] = {}
                    step_dict["output_data"] = {}
                    step_dict["dependencies"] = []
                    converted_steps.append(step_dict)
                else:
                    converted_steps.append(step)
            reasoning_chain_dict["steps"] = converted_steps
        else:
            reasoning_chain_dict["steps"] = []
        
        return reasoning_chain_dict
    except Exception as e:
        logger.error(f"Error converting reasoning_chain to dict: {e}", exc_info=True)
        return None


class MCPWarehouseState(TypedDict):
    """Enhanced state management for MCP-enabled warehouse assistant workflow."""

    messages: Annotated[List[BaseMessage], add_messages]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    routing_confidence: Optional[float]
    agent_responses: Dict[str, Any]
    final_response: Optional[str]
    context: Dict[str, any]
    session_id: str
    mcp_results: Optional[Any]  # MCP execution results
    tool_execution_plan: Optional[List[Dict[str, Any]]]  # Planned tool executions
    available_tools: Optional[List[Dict[str, Any]]]  # Available MCP tools
    enable_reasoning: bool  # Enable advanced reasoning
    reasoning_types: Optional[List[str]]  # Specific reasoning types to use
    reasoning_chain: Optional[Dict[str, Any]]  # Reasoning chain from agents
    planner_scratchpad: Optional[Dict[str, Any]]  # Deterministic plan/risk profile
    primary_route: Optional[str]  # Original route before optional collaboration
    collaboration_plan: Optional[Dict[str, Any]]  # Multi-agent fan-out decision
    evidence_bundle: Optional[Dict[str, Any]]  # Joined multi-agent evidence
    reflection_decision: Optional[Dict[str, Any]]  # Last reflection decision
    reflection_history: List[Dict[str, Any]]  # Append-only reflection decisions
    reflection_iterations: int  # Completed reflection reviews
    max_reflection_iterations: int  # Loop guard


class MCPIntentClassifier:
    """MCP-enhanced intent classifier with dynamic tool discovery."""

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.tool_routing = None  # Will be set by MCP planner graph

    EQUIPMENT_KEYWORDS = [
        "equipment",
        "forklift",
        "conveyor",
        "scanner",
        "amr",
        "agv",
        "charger",
        "assignment",
        "utilization",
        "maintenance",
        "availability",
        "telemetry",
        "battery",
        "truck",
        "lane",
        "pm",
        "loto",
        "lockout",
        "tagout",
        "sku",
        "stock",
        "inventory",
        "quantity",
        "available",
        "atp",
        "on_hand",
    ]

    OPERATIONS_KEYWORDS = [
        "shift",
        "task",
        "tasks",
        "workforce",
        "pick",
        "pack",
        "putaway",
        "schedule",
        "assignment",
        "kpi",
        "performance",
        "equipment",
        "main",
        "today",
        "work",
        "job",
        "operation",
        "operations",
        "worker",
        "workers",
        "team",
        "team members",
        "staff",
        "employee",
        "employees",
        "active workers",
        "how many",
        "roles",
        "team members",
        "wave",
        "waves",
        "order",
        "orders",
        "zone",
        "zones",
        "line",
        "lines",
        "create",
        "generating",
        "pick wave",
        "pick waves",
        "order management",
        "zone a",
        "zone b",
        "zone c",
    ]

    SAFETY_KEYWORDS = [
        "safety",
        "incident",
        "compliance",
        "policy",
        "checklist",
        "hazard",
        "accident",
        "protocol",
        "training",
        "audit",
        "over-temp",
        "overtemp",
        "temperature",
        "event",
        "detected",
        "alert",
        "warning",
        "emergency",
        "malfunction",
        "failure",
        "ppe",
        "protective",
        "helmet",
        "gloves",
        "boots",
        "safety harness",
        "procedures",
        "guidelines",
        "standards",
        "regulations",
        "evacuation",
        "fire",
        "chemical",
        "lockout",
        "tagout",
        "loto",
        "injury",
        "report",
        "investigation",
        "corrective",
        "action",
        "issues",
        "problem",
        "concern",
        "violation",
        "breach",
    ]

    DOCUMENT_KEYWORDS = [
        "document",
        "upload",
        "scan",
        "extract",
        "process",
        "pdf",
        "image",
        "invoice",
        "receipt",
        "bol",
        "bill of lading",
        "purchase order",
        "po",
        "quality",
        "validation",
        "approve",
        "review",
        "ocr",
        "text extraction",
        "file",
        "photo",
        "picture",
        "documentation",
        "paperwork",
        "neural",
        "nemo",
        "retriever",
        "parse",
        "vision",
        "multimodal",
        "document processing",
        "document analytics",
        "document search",
        "document status",
    ]

    async def classify_intent_with_mcp(self, message: str) -> str:
        """Classify user intent using MCP tool discovery for enhanced accuracy."""
        try:
            # First, use traditional keyword-based classification
            base_intent = self.classify_intent(message)

            # If we have MCP tools available, use them to enhance classification
            # Only override if base_intent is "general" (uncertain) - don't override specific classifications
            if self.tool_discovery and len(self.tool_discovery.discovered_tools) > 0 and base_intent == "general":
                # Search for tools that might help with intent classification
                relevant_tools = await self.tool_discovery.search_tools(message)
                
                # If we found relevant tools, use them to refine the intent
                if relevant_tools:
                    # Use tool categories to refine intent when base classification is uncertain
                    for tool in relevant_tools[:3]:  # Check top 3 most relevant tools
                        if (
                            "equipment" in tool.name.lower()
                            or "equipment" in tool.description.lower()
                        ):
                            return "equipment"
                        elif (
                            "operations" in tool.name.lower()
                            or "workforce" in tool.description.lower()
                        ):
                            return "operations"
                        elif (
                            "safety" in tool.name.lower()
                            or "incident" in tool.description.lower()
                        ):
                            return "safety"

            return base_intent

        except Exception as e:
            logger.error(f"Error in MCP intent classification: {e}")
            return self.classify_intent(message)

    FORECASTING_KEYWORDS = [
        "forecast",
        "forecasting",
        "demand forecast",
        "demand prediction",
        "predict demand",
        "sales forecast",
        "inventory forecast",
        "reorder recommendation",
        "model performance",
        "forecast accuracy",
        "mape",
        "model metrics",
        "business intelligence",
        "forecast dashboard",
        "sku forecast",
        "demand planning",
        "predict",
        "prediction",
        "trend",
        "projection",
    ]

    @classmethod
    def classify_intent(cls, message: str) -> str:
        """Enhanced intent classification with better logic and ambiguity handling."""
        message_lower = message.lower()
        
        # Check for forecasting-related keywords (high priority)
        forecasting_score = sum(
            1 for keyword in cls.FORECASTING_KEYWORDS if keyword in message_lower
        )
        if forecasting_score > 0:
            return "forecasting"

        # Check for specific safety-related queries first (highest priority)
        # Safety queries should take precedence over equipment/operations
        safety_score = sum(
            1 for keyword in cls.SAFETY_KEYWORDS if keyword in message_lower
        )
        
        # Emergency/urgent safety keywords that should always route to safety
        emergency_keywords = [
            "flooding", "flood", "fire", "spill", "leak", "urgent", "critical", 
            "emergency", "evacuate", "evacuation", "issue", "problem", "malfunction",
            "failure", "accident", "injury", "hazard", "danger", "unsafe"
        ]
        has_emergency = any(keyword in message_lower for keyword in emergency_keywords)
        
        # Safety context indicators (broader list)
        safety_context_indicators = [
            "procedure", "procedures", "policy", "policies", "incident", "incidents",
            "compliance", "safety", "ppe", "hazard", "hazards", "report", "reporting",
            "training", "audit", "checklist", "protocol", "guidelines", "standards",
            "regulations", "lockout", "tagout", "loto", "corrective", "action",
            "investigation", "violation", "breach", "concern", "flooding", "flood",
            "issue", "issues", "problem", "problems", "emergency", "urgent", "critical"
        ]
        
        # Route to safety if:
        # 1. Has emergency keywords (highest priority)
        # 2. Has safety keywords AND safety context indicators
        # 3. Has high safety score (multiple safety keywords)
        if has_emergency or (safety_score > 0 and any(
            indicator in message_lower for indicator in safety_context_indicators
        )) or safety_score >= 2:
            return "safety"

        # Check for document-related keywords (but only if it's clearly document-related)
        document_indicators = [
            "document",
            "upload",
            "scan",
            "extract",
            "pdf",
            "image",
            "invoice",
            "receipt",
            "bol",
            "bill of lading",
            "purchase order",
            "po",
            "quality",
            "validation",
            "approve",
            "review",
            "ocr",
            "text extraction",
            "file",
            "photo",
            "picture",
            "documentation",
            "paperwork",
            "neural",
            "nemo",
            "retriever",
            "parse",
            "vision",
            "multimodal",
            "document processing",
            "document analytics",
            "document search",
            "document status",
        ]
        if any(keyword in message_lower for keyword in document_indicators):
            return "document"

        # Check for equipment-specific queries (availability, status, assignment)
        # But only if it's not a workflow operation AND not a safety issue
        equipment_indicators = [
            "available", "availability", "status", "utilization", "maintenance",
            "telemetry", "assignment", "assign", "dispatch", "deploy"
        ]
        equipment_objects = [
            "forklift", "forklifts", "scanner", "scanners", "conveyor", "conveyors",
            "truck", "trucks", "amr", "agv", "equipment", "machine", "machines",
            "asset", "assets"
        ]

        # Exclude safety-related equipment queries
        safety_equipment_terms = [
            "safety", "incident", "accident", "hazard", "danger", "unsafe",
            "issue", "problem", "malfunction", "failure", "emergency", "urgent"
        ]
        is_safety_equipment_query = any(term in message_lower for term in safety_equipment_terms)

        # Only route to equipment if it's a pure equipment query (not workflow-related, not safety-related)
        workflow_terms = ["wave", "order", "create", "pick", "pack", "task", "workflow"]
        is_workflow_query = any(term in message_lower for term in workflow_terms)

        if (
            not is_workflow_query
            and not is_safety_equipment_query
            and any(indicator in message_lower for indicator in equipment_indicators)
            and any(obj in message_lower for obj in equipment_objects)
        ):
            return "equipment"

        # Check for operations-related keywords (workflow, tasks, management)
        operations_score = sum(
            1 for keyword in cls.OPERATIONS_KEYWORDS if keyword in message_lower
        )
        if operations_score > 0:
            # Prioritize operations for workflow-related terms
            workflow_terms = [
                "task",
                "wave",
                "order",
                "create",
                "pick",
                "pack",
                "management",
                "workflow",
                "dispatch",
            ]
            if any(term in message_lower for term in workflow_terms):
                return "operations"

        # Check for equipment-related keywords (fallback)
        equipment_score = sum(
            1 for keyword in cls.EQUIPMENT_KEYWORDS if keyword in message_lower
        )
        if equipment_score > 0:
            return "equipment"

        # Handle ambiguous queries
        ambiguous_patterns = [
            "inventory",
            "management",
            "help",
            "assistance",
            "support",
        ]
        if any(pattern in message_lower for pattern in ambiguous_patterns):
            return "ambiguous"

        # Default to equipment for general queries
        return "equipment"


class MCPPlannerGraph:
    """MCP-enabled planner graph for warehouse operations."""

    def __init__(self, checkpointer: BaseCheckpointSaver):
        self.checkpointer = checkpointer
        self.tool_discovery: Optional[ToolDiscoveryService] = None
        self.tool_binding: Optional[ToolBindingService] = None
        self.tool_routing: Optional[ToolRoutingService] = None
        self.tool_validation: Optional[ToolValidationService] = None
        self.mcp_manager: Optional[MCPManager] = None
        self.intent_classifier: Optional[MCPIntentClassifier] = None
        self.graph = None
        self.initialized = False

    async def initialize(self) -> None:
        """Initialize MCP components and create the graph."""
        try:
            # Initialize MCP services (simplified for Phase 2 Step 3)
            self.tool_discovery = ToolDiscoveryService()
            self.tool_binding = ToolBindingService(self.tool_discovery)
            # Skip complex routing for now - will implement in next step
            self.tool_routing = None
            self.tool_validation = ToolValidationService(self.tool_discovery)
            self.mcp_manager = MCPManager()

            # Start tool discovery with timeout
            try:
                await asyncio.wait_for(
                    self.tool_discovery.start_discovery(),
                    timeout=2.0  # 2 second timeout for tool discovery
                )
            except asyncio.TimeoutError:
                logger.warning("Tool discovery timed out, continuing without full discovery")
            except Exception as discovery_error:
                logger.warning(f"Tool discovery failed: {discovery_error}, continuing without full discovery")

            # Initialize intent classifier with MCP
            self.intent_classifier = MCPIntentClassifier(self.tool_discovery)
            self.intent_classifier.tool_routing = self.tool_routing

            # Create the graph
            self.graph = self._create_graph()

            self.initialized = True
            logger.info("MCP Planner Graph initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Planner Graph: {e}")
            # Don't raise - allow system to continue with limited functionality
            # Set initialized to False so it can be retried
            self.initialized = False
            # Still try to create a basic graph for fallback
            try:
                self.graph = self._create_graph()
            except:
                self.graph = None

    def _create_graph(self) -> StateGraph:
        """Create the MCP-enabled planner graph."""
        # Initialize the state graph
        workflow = StateGraph(MCPWarehouseState)

        # Add nodes
        workflow.add_node("plan_task", self._instrumented_node("plan_task", self._plan_task))
        workflow.add_node("route_intent", self._instrumented_node("route_intent", self._mcp_route_intent))
        workflow.add_node("collaboration_plan", self._instrumented_node("collaboration_plan", self._build_collaboration_plan))
        workflow.add_node("multi_agent_collect", self._instrumented_node("multi_agent_collect", self._mcp_multi_agent_collect))
        workflow.add_node("evidence_join", self._instrumented_node("evidence_join", self._mcp_evidence_join))
        workflow.add_node("equipment", self._instrumented_node("equipment", self._mcp_equipment_agent))
        workflow.add_node("operations", self._instrumented_node("operations", self._mcp_operations_agent))
        workflow.add_node("safety", self._instrumented_node("safety", self._mcp_safety_agent))
        workflow.add_node("forecasting", self._instrumented_node("forecasting", self._mcp_forecasting_agent))
        workflow.add_node("document", self._instrumented_node("document", self._mcp_document_agent))
        workflow.add_node("general", self._instrumented_node("general", self._mcp_general_agent))
        workflow.add_node("ambiguous", self._instrumented_node("ambiguous", self._handle_ambiguous_query))
        workflow.add_node("reflect", self._instrumented_node("reflect", self._mcp_reflect))
        workflow.add_node("synthesize", self._instrumented_node("synthesize", self._mcp_synthesize_response))

        # Set entry point
        workflow.set_entry_point("plan_task")
        workflow.add_edge("plan_task", "route_intent")
        workflow.add_edge("route_intent", "collaboration_plan")

        # Add conditional edges for routing
        workflow.add_conditional_edges(
            "collaboration_plan",
            self._route_after_collaboration_plan,
            {
                "multi_agent_collect": "multi_agent_collect",
                "equipment": "equipment",
                "operations": "operations",
                "safety": "safety",
                "forecasting": "forecasting",
                "document": "document",
                "general": "general",
                "ambiguous": "ambiguous",
            },
        )

        # Add edges from agents to reflection before final synthesis
        workflow.add_edge("equipment", "reflect")
        workflow.add_edge("operations", "reflect")
        workflow.add_edge("safety", "reflect")
        workflow.add_edge("forecasting", "reflect")
        workflow.add_edge("document", "reflect")
        workflow.add_edge("general", "reflect")
        workflow.add_edge("multi_agent_collect", "evidence_join")
        workflow.add_edge("evidence_join", "reflect")
        workflow.add_edge("ambiguous", "synthesize")

        workflow.add_conditional_edges(
            "reflect",
            self._route_after_reflection,
            {
                "finalize": "synthesize",
                "clarify": "ambiguous",
                "replan": "route_intent",
            },
        )

        # Add edge from synthesis to end
        workflow.add_edge("synthesize", END)

        return workflow.compile(checkpointer=self.checkpointer)

    def _instrumented_node(self, node_name: str, handler):
        """Wrap a LangGraph node with run events and cooperative cancellation."""

        async def wrapped(state: MCPWarehouseState) -> MCPWarehouseState:
            await _check_run_cancelled()
            if node_name not in {"plan_task", "route_intent", "reflect", "synthesize"}:
                await _emit_run_event(
                    RunEventType.AGENT_STARTED,
                    f"智能体开始执行：{node_name}",
                    agent_name=node_name,
                )
            try:
                maybe_result = handler(state)
                result = (
                    await maybe_result
                    if inspect.isawaitable(maybe_result)
                    else maybe_result
                )
            except RunCancelled:
                raise
            except Exception as error:
                await _emit_run_event(
                    RunEventType.RUN_FAILED,
                    "图节点执行失败",
                    severity=RunEventSeverity.ERROR,
                    agent_name=node_name,
                    payload={"error": sanitize_log_data(str(error))},
                )
                raise

            if node_name == "route_intent":
                await _emit_run_event(
                    RunEventType.ROUTE_SELECTED,
                    f"路由到：{result.get('routing_decision') or 'unknown'}",
                    payload={
                        "intent": result.get("user_intent"),
                        "route": result.get("routing_decision"),
                    },
                )
            elif node_name == "synthesize":
                await _emit_run_event(
                    RunEventType.CHECKPOINT_SAVED,
                    "图执行结果已进入检查点流程",
                    payload={"node": node_name},
                )
            elif node_name in {"plan_task", "reflect"}:
                pass
            else:
                await _emit_run_event(
                    RunEventType.AGENT_COMPLETED,
                    f"智能体执行完成：{node_name}",
                    agent_name=node_name,
                )
            await _check_run_cancelled()
            return result

        wrapped.__name__ = f"instrumented_{node_name}"
        return wrapped

    async def _plan_task(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Create a structured task plan before intent routing."""

        message_text = _extract_message_text(state) or ""
        context = state.setdefault("context", {})
        plan = build_planner_decision(message_text, context)
        max_iterations = int(
            plan.get("max_reflection_iterations", DEFAULT_MAX_REFLECTION_ITERATIONS)
        )

        state["planner_scratchpad"] = plan
        state["reflection_decision"] = None
        state["reflection_history"] = list(state.get("reflection_history") or [])
        state["reflection_iterations"] = int(state.get("reflection_iterations") or 0)
        state["max_reflection_iterations"] = max_iterations
        context["planner_scratchpad"] = plan
        context["max_reflection_iterations"] = max_iterations
        autonomous_reasoning = context.get("autonomous_reasoning")
        if not isinstance(autonomous_reasoning, dict):
            autonomous_reasoning = {}
            context["autonomous_reasoning"] = autonomous_reasoning
        autonomous_reasoning["planner"] = plan

        await _emit_run_event(
            RunEventType.PLAN_CREATED,
            f"已生成任务计划：路由建议 {plan.get('route_hint')}，风险 {plan.get('risk_level')}",
            payload={
                "route_hint": plan.get("route_hint"),
                "risk_level": plan.get("risk_level"),
                "requires_approval": plan.get("requires_approval"),
                "missing_facts": plan.get("missing_facts", []),
                "detected_actions": plan.get("detected_actions", []),
                "plan_steps": plan.get("plan_steps", []),
            },
        )
        await _update_current_run_risk_level(str(plan.get("risk_level") or "low"))
        return state

    async def _mcp_reflect(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Review the selected agent result before final synthesis."""

        context = state.setdefault("context", {})
        decision = await review_agent_outcome_with_judge(state)
        history = list(state.get("reflection_history") or [])
        history.append(decision)

        state["reflection_decision"] = decision
        state["reflection_history"] = history
        state["reflection_iterations"] = int(
            decision.get("iteration", state.get("reflection_iterations", 0) + 1)
        )
        context["reflection_decision"] = decision
        context["reflection_history"] = history
        autonomous_reasoning = context.get("autonomous_reasoning")
        if not isinstance(autonomous_reasoning, dict):
            autonomous_reasoning = {}
            context["autonomous_reasoning"] = autonomous_reasoning
        autonomous_reasoning["reflection_history"] = history

        action = decision.get("action", "finalize")
        if action == "clarify":
            state["routing_decision"] = "ambiguous"
            context["reflection_clarification"] = {
                "question": decision.get("clarifying_question"),
                "options": decision.get("clarifying_options", []),
                "missing_facts": decision.get("missing_facts", []),
            }
        elif action == "replan":
            next_route = decision.get("next_route") or "general"
            context["reflection_next_route"] = next_route

        await _emit_reflection_event(decision)
        return state

    async def _mcp_route_intent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Route user message using MCP-enhanced intent classification with semantic routing."""
        try:
            # Get the latest user message
            message_text = _extract_message_text(state)
            if not message_text:
                state["user_intent"] = "general"
                state["routing_decision"] = "general"
                state["routing_confidence"] = 0.0
                return state

            context = state.setdefault("context", {})
            reflection_next_route = context.pop("reflection_next_route", None)
            if reflection_next_route in {
                "equipment",
                "operations",
                "safety",
                "forecasting",
                "document",
                "general",
                "ambiguous",
            }:
                state["user_intent"] = str(reflection_next_route)
                state["routing_decision"] = str(reflection_next_route)
                state["routing_confidence"] = 0.75
                context["reflection_route_override_used"] = {
                    "route": reflection_next_route,
                    "iteration": state.get("reflection_iterations", 0),
                }
                logger.info(
                    "Reflection requested one-shot route override to %s",
                    reflection_next_route,
                )
                return state

            # Use MCP-enhanced intent classification (keyword-based)
            intent_result = await self.intent_classifier.classify_intent_with_mcp(message_text)
            
            # Extract intent string from result (it's a dict)
            keyword_intent = intent_result.get("intent", "general") if isinstance(intent_result, dict) else intent_result
            keyword_confidence = intent_result.get("confidence", 0.7) if isinstance(intent_result, dict) else 0.7
            
            # Special handling: If keyword classification found worker-related terms, prioritize operations
            # This prevents semantic router from overriding correct worker classification
            message_lower = message_text.lower()
            worker_keywords = ["worker", "workers", "workforce", "employee", "employees", "staff", "team members", "personnel"]
            has_worker_keywords = any(keyword in message_lower for keyword in worker_keywords)
            
            if has_worker_keywords and keyword_intent != "operations":
                logger.info(f"🔧 Overriding intent from '{keyword_intent}' to 'operations' due to worker keywords")
                keyword_intent = "operations"
                keyword_confidence = 0.9  # High confidence for explicit worker queries
            
            # Enhance with semantic routing
            try:
                from src.api.services.routing.semantic_router import get_semantic_router
                semantic_router = await get_semantic_router()
                
                # If we have high confidence worker keywords, skip semantic routing to avoid override
                if has_worker_keywords:
                    intent = "operations"
                    confidence = 0.9
                    logger.info(f"🔧 Using operations intent directly for worker query (skipping semantic override)")
                else:
                    intent, confidence = await semantic_router.classify_intent_semantic(
                        message_text,
                        keyword_intent,
                        keyword_confidence=keyword_confidence
                    )
                    logger.info(f"Semantic routing: keyword={keyword_intent}, semantic={intent}, confidence={confidence:.2f}")
            except Exception as e:
                logger.warning(f"Semantic routing failed, using keyword-based: {e}")
                intent = keyword_intent
                confidence = keyword_confidence
            
            state["user_intent"] = intent
            state["routing_decision"] = intent
            state["routing_confidence"] = confidence

            # Discover available tools for this query
            if self.tool_discovery:
                available_tools = await self.tool_discovery.get_available_tools()
                state["available_tools"] = [
                    {
                        "tool_id": tool.tool_id,
                        "name": tool.name,
                        "description": tool.description,
                        "category": tool.category.value,
                    }
                    for tool in available_tools
                ]

            # Sanitize user-controlled message before logging
            safe_message_text = sanitize_log_data(message_text, max_length=100)
            logger.info(
                f"🔀 MCP Intent classified as: {intent} for message: {safe_message_text}..."
            )
            logger.debug(
                f"Routing decision details - Intent: {intent}, Message: {safe_message_text}, "
                f"Safety keywords found: {sum(1 for kw in MCPIntentClassifier.SAFETY_KEYWORDS if kw in message_text.lower())}, "
                f"Equipment keywords found: {sum(1 for kw in MCPIntentClassifier.EQUIPMENT_KEYWORDS if kw in message_text.lower())}"
            )

            # Handle ambiguous queries with clarifying questions
            if intent == "ambiguous":
                return await self._handle_ambiguous_query(state)

        except Exception as e:
            logger.error(f"❌ Error in MCP intent routing: {e}", exc_info=True)
            state["user_intent"] = "general"
            state["routing_decision"] = "general"

        return state

    async def _build_collaboration_plan(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Decide whether this request should use multi-agent evidence join."""

        message_text = _extract_message_text(state) or ""
        context = state.setdefault("context", {})
        planner = state.get("planner_scratchpad") or context.get("planner_scratchpad") or {}
        primary_route = str(
            state.get("routing_decision")
            or (planner.get("route_hint") if isinstance(planner, dict) else None)
            or "general"
        )
        plan = build_collaboration_plan(
            message_text,
            planner if isinstance(planner, dict) else {},
            primary_route,
            context,
        )

        state["primary_route"] = plan.get("primary_route", primary_route)
        state["collaboration_plan"] = plan
        context["collaboration_plan"] = plan

        autonomous_reasoning = context.get("autonomous_reasoning")
        if not isinstance(autonomous_reasoning, dict):
            autonomous_reasoning = {}
            context["autonomous_reasoning"] = autonomous_reasoning
        autonomous_reasoning["collaboration_plan"] = plan

        if plan.get("enabled"):
            await _emit_run_event(
                RunEventType.MULTI_AGENT_SELECTED,
                "已选择多智能体协作收集证据",
                agent_name="collaboration_plan",
                payload={
                    "primary_route": plan.get("primary_route"),
                    "selected_agents": plan.get("selected_agents", []),
                    "reasons": plan.get("reasons", []),
                    "mode": plan.get("mode"),
                    "max_agents": plan.get("max_agents"),
                },
            )

        return state

    async def _mcp_multi_agent_collect(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Run selected read-only specialist agents and collect their evidence."""

        message_text = _extract_message_text(state) or ""
        context = state.setdefault("context", {})
        plan = state.get("collaboration_plan") or {}
        handler_map = {
            "equipment": self._mcp_equipment_agent,
            "operations": self._mcp_operations_agent,
            "safety": self._mcp_safety_agent,
            "forecasting": self._mcp_forecasting_agent,
            "document": self._mcp_document_agent,
        }
        selected_agents = [
            str(agent)
            for agent in plan.get("selected_agents", [])
            if str(agent) in handler_map
        ]
        if not selected_agents:
            primary_route = str(
                state.get("primary_route")
                or plan.get("primary_route")
                or state.get("routing_decision")
                or "general"
            )
            if primary_route in handler_map:
                selected_agents = [primary_route]

        async def _run_selected_agent(agent_name: str) -> tuple[str, Any, str | None]:
            await _check_run_cancelled()
            agent_state = self._clone_state_for_agent(state, agent_name)
            try:
                maybe_result = handler_map[agent_name](agent_state)
                result_state = (
                    await maybe_result
                    if inspect.isawaitable(maybe_result)
                    else maybe_result
                )
                response = (result_state.get("agent_responses") or {}).get(agent_name)
                return agent_name, response, None
            except RunCancelled:
                raise
            except Exception as exc:
                logger.warning(
                    "Multi-agent specialist %s failed: %s",
                    agent_name,
                    sanitize_log_data(str(exc)),
                )
                return (
                    agent_name,
                    _create_error_response(agent_name, message_text, exc),
                    str(exc),
                )

        results = await asyncio.gather(
            *(_run_selected_agent(agent_name) for agent_name in selected_agents)
        )

        merged_responses = dict(state.get("agent_responses") or {})
        errors = []
        for agent_name, response, error in results:
            merged_responses[agent_name] = response
            if error:
                errors.append({"agent_name": agent_name, "error": error})

        state["agent_responses"] = merged_responses
        context["multi_agent_collection"] = {
            "selected_agents": selected_agents,
            "errors": errors,
        }
        return state

    async def _mcp_evidence_join(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Join collected specialist evidence into one response for reflection."""

        message_text = _extract_message_text(state) or ""
        context = state.setdefault("context", {})
        plan = state.get("collaboration_plan") or {}
        selected_agents = [
            str(agent)
            for agent in plan.get("selected_agents", [])
            if str(agent) in {
                "equipment",
                "operations",
                "safety",
                "forecasting",
                "document",
            }
        ]
        primary_route = str(
            state.get("primary_route")
            or plan.get("primary_route")
            or state.get("routing_decision")
            or "general"
        )
        planner = dict(
            state.get("planner_scratchpad")
            or context.get("planner_scratchpad")
            or {}
        )
        planner["selected_agents"] = selected_agents

        agent_responses = state.get("agent_responses") or {}
        evidence_items = [
            summarize_agent_evidence(agent_name, agent_responses.get(agent_name))
            for agent_name in selected_agents
        ]
        bundle = join_agent_evidence(
            message_text,
            planner,
            primary_route,
            evidence_items,
        )
        recommendations = self._recommendations_from_evidence_bundle(bundle)

        state["evidence_bundle"] = bundle
        state["routing_decision"] = "evidence_join"
        state["agent_responses"]["evidence_join"] = {
            "natural_language": bundle.get("summary", ""),
            "data": bundle,
            "recommendations": recommendations,
            "confidence": bundle.get("average_confidence", 0.0),
            "response_type": "multi_agent_evidence",
            "mcp_tools_used": self._tools_from_evidence_bundle(bundle),
            "tool_execution_results": {},
            "actions_taken": [],
        }

        context["evidence_bundle"] = bundle
        autonomous_reasoning = context.get("autonomous_reasoning")
        if not isinstance(autonomous_reasoning, dict):
            autonomous_reasoning = {}
            context["autonomous_reasoning"] = autonomous_reasoning
        autonomous_reasoning["evidence_bundle"] = bundle

        await _emit_run_event(
            RunEventType.EVIDENCE_JOINED,
            "多智能体证据已汇总",
            agent_name="evidence_join",
            payload={
                "primary_route": bundle.get("primary_route"),
                "contributing_agents": bundle.get("contributing_agents", []),
                "evidence_count": bundle.get("evidence_count", 0),
                "average_confidence": bundle.get("average_confidence", 0.0),
                "gaps": bundle.get("gaps", []),
            },
        )

        return state

    async def _handle_ambiguous_query(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Handle ambiguous queries with clarifying questions."""
        try:
            message_text = _extract_message_text(state)
            if not message_text:
                return state

            message_lower = message_text.lower()
            reflection_clarification = state.get("context", {}).get(
                "reflection_clarification"
            )
            if isinstance(reflection_clarification, dict):
                question = str(
                    reflection_clarification.get("question")
                    or "请补充关键业务信息后我再继续执行。"
                )
                options = reflection_clarification.get("options") or []
                clarifying_message = AIMessage(content=question)
                state["messages"].append(clarifying_message)
                state["routing_decision"] = "ambiguous"
                state["context"]["clarifying"] = {
                    "text": question,
                    "options": options,
                    "original_query": message_text,
                    "source": "reflection",
                    "missing_facts": reflection_clarification.get("missing_facts", []),
                }
                state["agent_responses"]["ambiguous"] = {
                    "natural_language": question,
                    "data": {"options": options},
                    "recommendations": options,
                    "confidence": 1.0,
                    "response_type": "clarification_required",
                }
                state["final_response"] = question
                return state

            # Define clarifying questions based on ambiguous patterns
            clarifying_responses = {
                "inventory": {
                    "question": "I can help with inventory management. Are you looking for:",
                    "options": [
                        "Equipment inventory and status",
                        "Product inventory management",
                        "Inventory tracking and reporting",
                    ],
                },
                "management": {
                    "question": "What type of management do you need help with?",
                    "options": [
                        "Equipment management",
                        "Task management",
                        "Safety management",
                    ],
                },
                "help": {
                    "question": "I'm here to help! What would you like to do?",
                    "options": [
                        "Check equipment status",
                        "Create a task",
                        "View safety procedures",
                        "Upload a document",
                    ],
                },
                "assistance": {
                    "question": "I can assist you with warehouse operations. What do you need?",
                    "options": [
                        "Equipment assistance",
                        "Task assistance",
                        "Safety assistance",
                        "Document assistance",
                    ],
                },
            }

            # Find matching pattern
            for pattern, response in clarifying_responses.items():
                if pattern in message_lower:
                    # Create clarifying question response
                    clarifying_message = AIMessage(content=response["question"])
                    state["messages"].append(clarifying_message)

                    # Store clarifying context
                    state["context"]["clarifying"] = {
                        "text": response["question"],
                        "options": response["options"],
                        "original_query": message_text,
                    }

                    state["agent_responses"]["clarifying"] = response["question"]
                    state["final_response"] = response["question"]
                    return state

            # Default clarifying question
            default_response = {
                "question": "I can help with warehouse operations. What would you like to do?",
                "options": [
                    "Check equipment status",
                    "Create a task",
                    "View safety procedures",
                    "Upload a document",
                ],
            }

            clarifying_message = AIMessage(content=default_response["question"])
            state["messages"].append(clarifying_message)

            state["context"]["clarifying"] = {
                "text": default_response["question"],
                "options": default_response["options"],
                "original_query": message_text,
            }

            state["agent_responses"]["clarifying"] = default_response["question"]
            state["final_response"] = default_response["question"]

        except Exception as e:
            logger.error(f"Error handling ambiguous query: {e}")
            state["final_response"] = (
                "I'm not sure how to help with that. Could you please be more specific?"
            )

        return state

    async def _mcp_equipment_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle equipment queries using MCP-enabled Equipment Agent."""
        try:
            from src.api.agents.inventory.mcp_equipment_agent import (
                get_mcp_equipment_agent,
            )

            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["equipment"] = {
                    "natural_language": "No message to process",
                    "data": {},
                    "recommendations": [],
                    "confidence": 0.0,
                    "response_type": "error",
                }
                return state

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP equipment agent with timeout
            try:
                mcp_equipment_agent = await asyncio.wait_for(
                    get_mcp_equipment_agent(),
                    timeout=AGENT_INIT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error("MCP equipment agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP equipment agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries and calculate timeout
            is_complex_query = _detect_complex_query(message_text)
            agent_timeout = _calculate_agent_timeout(enable_reasoning, is_complex_query)
            
            logger.info(f"Equipment agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_equipment_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP equipment agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Equipment agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP equipment agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            state["agent_responses"]["equipment"] = _convert_response_to_dict(response, "equipment_info")

            logger.info(
                f"MCP Equipment agent processed request with confidence: {response.confidence if hasattr(response, 'confidence') else state['agent_responses']['equipment'].get('confidence', 0.0)}"
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout in MCP equipment agent: {e}")
            state["agent_responses"]["equipment"] = _create_error_response("equipment", message_text, e, is_timeout=True)
        except Exception as e:
            logger.error(f"Error in MCP equipment agent: {e}", exc_info=True)
            state["agent_responses"]["equipment"] = _create_error_response("equipment", message_text, e, is_timeout=False)

        return state

    async def _mcp_operations_agent(
        self, state: MCPWarehouseState
    ) -> MCPWarehouseState:
        """Handle operations queries using MCP-enabled Operations Agent."""
        try:
            from src.api.agents.operations.mcp_operations_agent import (
                get_mcp_operations_agent,
            )

            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["operations"] = "No message to process"
                return state

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP operations agent with timeout
            try:
                mcp_operations_agent = await asyncio.wait_for(
                    get_mcp_operations_agent(),
                    timeout=AGENT_INIT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error("MCP operations agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP operations agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries and calculate timeout
            is_complex_query = _detect_complex_query(message_text)
            agent_timeout = _calculate_agent_timeout(enable_reasoning, is_complex_query)
            
            logger.info(f"Operations agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_operations_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP operations agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Operations agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP operations agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            state["agent_responses"]["operations"] = _convert_response_to_dict(response, "operations_info")

            logger.info(
                f"MCP Operations agent processed request with confidence: {response.confidence if hasattr(response, 'confidence') else state['agent_responses']['operations'].get('confidence', 0.0)}"
            )

        except Exception as e:
            logger.error(f"Error in MCP operations agent: {e}")
            state["agent_responses"]["operations"] = _create_error_response("operations", message_text or "", e, is_timeout=False)

        return state

    async def _mcp_safety_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle safety queries using MCP-enabled Safety Agent."""
        try:
            from src.api.agents.safety.mcp_safety_agent import get_mcp_safety_agent

            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["safety"] = {
                    "natural_language": "No message to process",
                    "data": {},
                    "recommendations": [],
                    "confidence": 0.0,
                    "response_type": "error",
                }
                return state

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP safety agent with timeout
            try:
                mcp_safety_agent = await asyncio.wait_for(
                    get_mcp_safety_agent(),
                    timeout=AGENT_INIT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error("MCP safety agent initialization timed out")
                raise
            except Exception as init_error:
                logger.error(f"MCP safety agent initialization failed: {init_error}")
                raise

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Detect complex queries and calculate timeout
            is_complex_query = _detect_complex_query(message_text)
            agent_timeout = _calculate_agent_timeout(enable_reasoning, is_complex_query)
            
            logger.info(f"Safety agent timeout: {agent_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            
            try:
                response = await asyncio.wait_for(
                    mcp_safety_agent.process_query(
                        query=message_text,
                        session_id=session_id,
                        context=state.get("context", {}),
                        mcp_results=state.get("mcp_results"),
                        enable_reasoning=enable_reasoning,
                        reasoning_types=reasoning_types,
                    ),
                    timeout=agent_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"MCP safety agent process_query timed out after {agent_timeout}s")
                raise TimeoutError(f"Safety agent processing timed out after {agent_timeout}s")
            except Exception as process_error:
                logger.error(f"MCP safety agent process_query failed: {process_error}")
                raise

            # Store the response (handle both dict and object responses)
            state["agent_responses"]["safety"] = _convert_response_to_dict(response, "safety_info")

            logger.info(
                f"MCP Safety agent processed request with confidence: {response.confidence if hasattr(response, 'confidence') else state['agent_responses']['safety'].get('confidence', 0.0)}"
            )

        except asyncio.TimeoutError as e:
            logger.error(f"Timeout in MCP safety agent: {e}")
            state["agent_responses"]["safety"] = _create_error_response("safety", message_text, e, is_timeout=True)
        except Exception as e:
            logger.error(f"Error in MCP safety agent: {e}", exc_info=True)
            state["agent_responses"]["safety"] = _create_error_response("safety", message_text, e, is_timeout=False)

        return state

    async def _mcp_forecasting_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle forecasting queries using MCP-enabled Forecasting Agent."""
        try:
            from src.api.agents.forecasting.forecasting_agent import (
                get_forecasting_agent,
            )

            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["forecasting"] = "No message to process"
                return state

            # Get session ID from context
            session_id = state.get("session_id", "default")

            # Get MCP forecasting agent
            forecasting_agent = await get_forecasting_agent()

            # Extract reasoning parameters from state
            enable_reasoning = state.get("enable_reasoning", False)
            reasoning_types = state.get("reasoning_types")
            
            # Process with MCP forecasting agent
            response = await forecasting_agent.process_query(
                query=message_text,
                session_id=session_id,
                context=state.get("context", {}),
                mcp_results=state.get("mcp_results"),
                enable_reasoning=enable_reasoning,
                reasoning_types=reasoning_types,
            )

            # Store the response
            state["agent_responses"]["forecasting"] = {
                "natural_language": response.natural_language,
                "data": response.data,
                "recommendations": response.recommendations,
                "confidence": response.confidence,
                "response_type": response.response_type,
                "mcp_tools_used": response.mcp_tools_used or [],
                "tool_execution_results": response.tool_execution_results or {},
                "actions_taken": response.actions_taken or [],
                "reasoning_chain": response.reasoning_chain,
                "reasoning_steps": response.reasoning_steps,
            }

            logger.info(
                f"MCP Forecasting agent processed request with confidence: {response.confidence}"
            )

        except Exception as e:
            logger.error(f"Error in MCP forecasting agent: {e}")
            state["agent_responses"]["forecasting"] = {
                "natural_language": f"Error processing forecasting request: {str(e)}",
                "data": {"error": str(e)},
                "recommendations": [],
                "confidence": 0.0,
                "response_type": "error",
                "mcp_tools_used": [],
                "tool_execution_results": {},
            }

        return state

    async def _mcp_document_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle document-related queries with MCP tool discovery."""
        try:
            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["document"] = "No message to process"
                return state

            # Use MCP document agent
            try:
                from src.api.agents.document.mcp_document_agent import (
                    get_mcp_document_agent,
                )

                # Get document agent
                document_agent = await get_mcp_document_agent()

                # Extract reasoning parameters from state
                enable_reasoning = state.get("enable_reasoning", False)
                reasoning_types = state.get("reasoning_types")
                
                # Process query
                response = await document_agent.process_query(
                    query=message_text,
                    session_id=state.get("session_id", "default"),
                    context=state.get("context", {}),
                    mcp_results=state.get("mcp_results"),
                    enable_reasoning=enable_reasoning,
                    reasoning_types=reasoning_types,
                )

                # Store response with reasoning chain
                if hasattr(response, "natural_language"):
                    response_text = response.natural_language
                    # Store as dict with reasoning chain
                    state["agent_responses"]["document"] = {
                        "natural_language": response.natural_language,
                        "data": response.data if hasattr(response, "data") else {},
                        "recommendations": response.recommendations if hasattr(response, "recommendations") else [],
                        "confidence": response.confidence if hasattr(response, "confidence") else 0.0,
                        "response_type": response.response_type if hasattr(response, "response_type") else "document_info",
                        "actions_taken": response.actions_taken if hasattr(response, "actions_taken") else [],
                        "reasoning_chain": response.reasoning_chain if hasattr(response, "reasoning_chain") else None,
                        "reasoning_steps": response.reasoning_steps if hasattr(response, "reasoning_steps") else None,
                    }
                else:
                    response_text = str(response)
                    state["agent_responses"]["document"] = f"[MCP DOCUMENT AGENT] {response_text}"
                logger.info("MCP Document agent processed request")

            except Exception as e:
                logger.error(f"Error calling MCP document agent: {e}")
                state["agent_responses"][
                    "document"
                ] = f"[MCP DOCUMENT AGENT] Error processing document request: {str(e)}"

        except Exception as e:
            logger.error(f"Error in MCP document agent: {e}")
            state["agent_responses"][
                "document"
            ] = f"Error processing document request: {str(e)}"

        return state

    async def _mcp_general_agent(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Handle general queries with MCP tool discovery."""
        try:
            # Extract message text
            message_text = _extract_message_text(state)
            if not message_text:
                state["agent_responses"]["general"] = "No message to process"
                return state

            # Use MCP tools to help with general queries
            if self.tool_discovery and len(self.tool_discovery.discovered_tools) > 0:
                # Search for relevant tools
                relevant_tools = await self.tool_discovery.search_tools(message_text)

                if relevant_tools:
                    # Use the most relevant tool
                    best_tool = relevant_tools[0]
                    try:
                        # Execute the tool
                        result = await self.tool_discovery.execute_tool(
                            best_tool.tool_id,
                            {"query": message_text},
                            action_index=0,
                        )

                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' and executed it. Result: {str(result)[:200]}..."
                    except Exception as e:
                        response = f"[MCP GENERAL AGENT] Found relevant tool '{best_tool.name}' but execution failed: {str(e)}"
                else:
                    response = (
                        "[MCP GENERAL AGENT] No relevant tools found for this query."
                    )
            else:
                response = "[MCP GENERAL AGENT] No MCP tools available. Processing general query... (stub implementation)"

            state["agent_responses"]["general"] = response
            logger.info("MCP General agent processed request")

        except Exception as e:
            logger.error(f"Error in MCP general agent: {e}")
            state["agent_responses"][
                "general"
            ] = f"Error processing general request: {str(e)}"

        return state

    def _mcp_synthesize_response(self, state: MCPWarehouseState) -> MCPWarehouseState:
        """Synthesize final response from MCP agent outputs."""
        try:
            routing_decision = state.get("routing_decision", "general")
            agent_responses = state.get("agent_responses", {})

            logger.info(f"🔍 Synthesizing response for routing_decision: {routing_decision}")
            logger.info(f"🔍 Available agent_responses keys: {list(agent_responses.keys())}")

            # Get the response from the appropriate agent
            if routing_decision in agent_responses:
                agent_response = agent_responses[routing_decision]
                logger.info(f"🔍 Found agent_response for {routing_decision}, type: {type(agent_response)}")
                
                # Log response structure for debugging
                if isinstance(agent_response, dict):
                    logger.info(f"🔍 agent_response dict keys: {list(agent_response.keys())}")
                    logger.info(f"🔍 Has natural_language: {'natural_language' in agent_response}")
                    if "natural_language" in agent_response:
                        logger.info(f"🔍 natural_language value: {str(agent_response['natural_language'])[:100]}...")
                elif hasattr(agent_response, "__dict__"):
                    logger.info(f"🔍 agent_response object attributes: {list(agent_response.__dict__.keys())}")

                # Handle MCP response format
                if hasattr(agent_response, "natural_language"):
                    # Convert dataclass to dict
                    if hasattr(agent_response, "__dict__"):
                        agent_response_dict = agent_response.__dict__.copy()
                    else:
                        # Use asdict for dataclasses
                        from dataclasses import asdict

                        agent_response_dict = asdict(agent_response)
                    
                    # Log what fields are in the dict
                    logger.info(f"📋 agent_response_dict keys: {list(agent_response_dict.keys())}")
                    logger.info(f"📋 Has reasoning_chain: {'reasoning_chain' in agent_response_dict}, value: {agent_response_dict.get('reasoning_chain') is not None}")

                    # Extract natural_language and ensure it's a string (never a dict/object)
                    natural_lang = agent_response_dict.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                    else:
                        # If natural_language is missing or invalid, use fallback
                        # DO NOT try to extract from other fields as they may contain structured data
                        logger.warning(f"natural_language is missing or invalid in agent_response_dict, using fallback")
                        final_response = f"I processed your {routing_decision} query, but couldn't generate a detailed response. Please try rephrasing your question."
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response_dict

                    # Add MCP tool information to context
                    if "mcp_tools_used" in agent_response_dict:
                        state["context"]["mcp_tools_used"] = agent_response_dict[
                            "mcp_tools_used"
                        ]
                    if "tool_execution_results" in agent_response_dict:
                        state["context"]["tool_execution_results"] = (
                            agent_response_dict["tool_execution_results"]
                        )
                    
                    # Add reasoning chain to context if available
                    if "reasoning_chain" in agent_response_dict:
                        reasoning_chain = agent_response_dict["reasoning_chain"]
                        logger.info(f"🔗 Found reasoning_chain in agent_response_dict: {reasoning_chain is not None}, type: {type(reasoning_chain)}")
                        reasoning_chain_dict = _convert_reasoning_chain_to_dict(reasoning_chain)
                        if reasoning_chain_dict:
                            state["context"]["reasoning_chain"] = reasoning_chain_dict
                            state["reasoning_chain"] = reasoning_chain_dict
                            logger.info(f"✅ Converted reasoning_chain to dict with {len(reasoning_chain_dict.get('steps', []))} steps")
                        else:
                            state["context"]["reasoning_chain"] = reasoning_chain
                            state["reasoning_chain"] = reasoning_chain
                    if "reasoning_steps" in agent_response_dict:
                        reasoning_steps = agent_response_dict["reasoning_steps"]
                        logger.info(f"🔗 Found reasoning_steps in agent_response_dict: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
                        state["context"]["reasoning_steps"] = reasoning_steps

                elif (
                    isinstance(agent_response, dict)
                    and "natural_language" in agent_response
                ):
                    # Extract natural_language and ensure it's a string (never a dict/object)
                    natural_lang = agent_response.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                    else:
                        # If natural_language is missing or invalid, use fallback
                        # DO NOT try to extract from other fields as they may contain structured data
                        logger.warning(f"natural_language is missing or invalid in dict response, using fallback")
                        final_response = f"I processed your {routing_decision} query, but couldn't generate a detailed response. Please try rephrasing your question."
                    # Store structured data in context for API response
                    state["context"]["structured_response"] = agent_response

                    # Add MCP tool information to context
                    if "mcp_tools_used" in agent_response:
                        state["context"]["mcp_tools_used"] = agent_response[
                            "mcp_tools_used"
                        ]
                    if "tool_execution_results" in agent_response:
                        state["context"]["tool_execution_results"] = agent_response[
                            "tool_execution_results"
                        ]
                    
                    # Add reasoning chain to context if available
                    if "reasoning_chain" in agent_response:
                        reasoning_chain = agent_response["reasoning_chain"]
                        logger.info(f"🔗 Found reasoning_chain in agent_response dict: {reasoning_chain is not None}, type: {type(reasoning_chain)}")
                        reasoning_chain_dict = _convert_reasoning_chain_to_dict(reasoning_chain)
                        if reasoning_chain_dict:
                            state["context"]["reasoning_chain"] = reasoning_chain_dict
                            state["reasoning_chain"] = reasoning_chain_dict
                            logger.info(f"✅ Converted reasoning_chain to dict with {len(reasoning_chain_dict.get('steps', []))} steps")
                        else:
                            # Already a dict or conversion failed, use as-is
                            state["context"]["reasoning_chain"] = reasoning_chain
                            state["reasoning_chain"] = reasoning_chain
                    if "reasoning_steps" in agent_response:
                        reasoning_steps = agent_response["reasoning_steps"]
                        logger.info(f"🔗 Found reasoning_steps in agent_response dict: {reasoning_steps is not None}, count: {len(reasoning_steps) if reasoning_steps else 0}")
                        state["context"]["reasoning_steps"] = reasoning_steps
                else:
                    # Handle legacy string response format or unexpected types
                    if isinstance(agent_response, str):
                        final_response = agent_response
                    elif isinstance(agent_response, dict):
                        # Only extract natural_language if it's a string - never convert dict/object to string
                        natural_lang = agent_response.get("natural_language")
                        if isinstance(natural_lang, str) and natural_lang.strip():
                            final_response = natural_lang
                        else:
                            # Use fallback - do not try other fields as they may contain structured data
                            logger.warning(f"natural_language missing or invalid in unexpected dict format, using fallback")
                            final_response = "I received your request and processed it successfully."
                        # Store the dict as structured response if it looks like one
                        if not state["context"].get("structured_response"):
                            state["context"]["structured_response"] = agent_response
                    else:
                        # For other types, try to get a meaningful string representation
                        # but avoid showing the entire object structure
                        final_response = "I received your request and processed it successfully."
                        logger.warning(f"Unexpected agent_response type: {type(agent_response)}, using fallback message")
            else:
                logger.warning(f"⚠️ No agent_response found for routing_decision: {routing_decision}, using fallback")
                final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."

            # Ensure final_response is set and not empty
            if not final_response or (isinstance(final_response, str) and final_response.strip() == ""):
                logger.error(f"❌ final_response is empty after synthesis, using fallback")
                logger.error(f"❌ agent_response type: {type(agent_response)}, keys: {list(agent_response.keys()) if isinstance(agent_response, dict) else 'N/A'}")
                # Try to extract any meaningful response from agent_response
                if isinstance(agent_response, dict):
                    # Only try natural_language field - never extract from other fields to avoid data leakage
                    natural_lang = agent_response.get("natural_language")
                    if isinstance(natural_lang, str) and natural_lang.strip():
                        final_response = natural_lang
                if not final_response or (isinstance(final_response, str) and final_response.strip() == ""):
                    final_response = "I'm sorry, I couldn't process your request. Please try rephrasing your question."

            state["final_response"] = final_response
            logger.info(f"✅ final_response set: {final_response[:100] if final_response else 'None'}...")

            # Add AI message to conversation
            if state["messages"]:
                ai_message = AIMessage(content=final_response)
                state["messages"].append(ai_message)

            logger.info(
                f"MCP Response synthesized for routing decision: {routing_decision}, final_response length: {len(final_response) if final_response else 0}"
            )

        except Exception as e:
            logger.error(f"Error synthesizing MCP response: {e}")
            state["final_response"] = (
                "I encountered an error processing your request. Please try again."
            )

        return state

    def _clone_state_for_agent(
        self, state: MCPWarehouseState, agent_name: str
    ) -> MCPWarehouseState:
        """Create an isolated state copy for one specialist fan-out branch."""

        cloned_state = dict(state)
        cloned_state["messages"] = list(state.get("messages") or [])
        cloned_state["context"] = dict(state.get("context") or {})
        cloned_state["agent_responses"] = dict(state.get("agent_responses") or {})
        cloned_state["user_intent"] = agent_name
        cloned_state["routing_decision"] = agent_name
        return cloned_state  # type: ignore[return-value]

    @staticmethod
    def _recommendations_from_evidence_bundle(bundle: Dict[str, Any]) -> List[str]:
        """Collect deduplicated recommendations and gaps from an evidence bundle."""

        recommendations: List[str] = []
        for item in bundle.get("evidence_items", []) or []:
            if not isinstance(item, dict):
                continue
            for recommendation in item.get("recommendations", []) or []:
                text = str(recommendation).strip()
                if text and text not in recommendations:
                    recommendations.append(text)
        for gap in bundle.get("gaps", []) or []:
            text = str(gap).strip()
            if text and text not in recommendations:
                recommendations.append(text)
        return recommendations[:10]

    @staticmethod
    def _tools_from_evidence_bundle(bundle: Dict[str, Any]) -> List[str]:
        """Collect deduplicated tool names from all evidence items."""

        tools: List[str] = []
        for item in bundle.get("evidence_items", []) or []:
            if not isinstance(item, dict):
                continue
            for tool_name in item.get("tools_used", []) or []:
                text = str(tool_name).strip()
                if text and text not in tools:
                    tools.append(text)
        return tools[:20]

    def _route_to_agent(self, state: MCPWarehouseState) -> str:
        """Route to the appropriate agent based on MCP intent classification."""
        routing_decision = state.get("routing_decision", "general")
        return routing_decision

    def _route_after_collaboration_plan(self, state: MCPWarehouseState) -> str:
        """Route either to multi-agent collection or the original specialist."""

        plan = state.get("collaboration_plan") or {}
        if plan.get("enabled"):
            return "multi_agent_collect"

        routing_decision = str(
            plan.get("primary_route")
            or state.get("routing_decision")
            or "general"
        )
        if routing_decision in {
            "equipment",
            "operations",
            "safety",
            "forecasting",
            "document",
            "general",
            "ambiguous",
        }:
            return routing_decision
        return "general"

    def _route_after_reflection(self, state: MCPWarehouseState) -> str:
        """Route based on the latest reflection decision."""

        decision = state.get("reflection_decision") or {}
        action = decision.get("action", "finalize")
        if action in {"finalize", "clarify", "replan"}:
            return action
        return "finalize"

    def _format_graph_result(
        self, result: Dict[str, Any], session_id: str
    ) -> Dict[str, Any]:
        """Format completed and interrupted graph results consistently."""
        if not isinstance(result, dict):
            raise _ApprovalWorkflowError("Approval workflow returned an invalid result.")

        raw_interrupts = result.get("__interrupt__")
        if raw_interrupts:
            interrupt_items = (
                raw_interrupts
                if isinstance(raw_interrupts, (list, tuple))
                else [raw_interrupts]
            )
            try:
                pending_approvals = [
                    ApprovalInterruptPayload.model_validate(
                        getattr(interrupt_item, "value", interrupt_item)
                    ).model_dump(mode="json")
                    for interrupt_item in interrupt_items
                ]
            except Exception as exc:
                logger.error(
                    "Invalid approval interrupt payload: %s",
                    sanitize_log_data(str(exc)),
                )
                raise _ApprovalWorkflowError(
                    "Approval workflow returned an invalid interrupt payload."
                ) from exc

            return {
                "response": "鎿嶄綔宸叉殏鍋滐紝绛夊緟缁忕悊瀹℃壒銆?",
                "intent": result.get("user_intent", "unknown"),
                "route": result.get("routing_decision", "unknown"),
                "session_id": session_id,
                "context": {},
                "execution_status": "approval_required",
                "pending_approvals": pending_approvals,
            }

        result_context = result.get("context", {}) or {}
        if result.get("planner_scratchpad"):
            result_context.setdefault("planner_scratchpad", result.get("planner_scratchpad"))
        if result.get("collaboration_plan"):
            result_context.setdefault("collaboration_plan", result.get("collaboration_plan"))
        if result.get("evidence_bundle"):
            result_context.setdefault("evidence_bundle", result.get("evidence_bundle"))
        if result.get("reflection_decision"):
            result_context.setdefault("reflection_decision", result.get("reflection_decision"))
        if result.get("reflection_history"):
            result_context.setdefault("reflection_history", result.get("reflection_history"))
        if not isinstance(result_context.get("autonomous_reasoning"), dict):
            result_context["autonomous_reasoning"] = {
                "planner": result_context.get("planner_scratchpad"),
                "collaboration_plan": result_context.get("collaboration_plan"),
                "evidence_bundle": result_context.get("evidence_bundle"),
                "reflection_history": result_context.get("reflection_history", []),
            }
        structured_response = result_context.get("structured_response", {})

        actions_taken = None
        if structured_response and isinstance(structured_response, dict):
            actions_taken = structured_response.get("actions_taken")
        if not actions_taken and result_context:
            actions_taken = result_context.get("actions_taken")

        return {
            "response": result.get("final_response", "No response generated"),
            "intent": result.get("user_intent", "unknown"),
            "route": result.get("routing_decision", "unknown"),
            "session_id": session_id,
            "context": result_context,
            "structured_response": structured_response,
            "actions_taken": actions_taken,
            "mcp_tools_used": result_context.get("mcp_tools_used", []),
            "tool_execution_results": result_context.get(
                "tool_execution_results", {}
            ),
            "available_tools": result.get("available_tools", []),
            "execution_status": "completed",
            "pending_approvals": [],
        }

    async def process_warehouse_query(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict] = None,
        approval_context: ApprovalExecutionContext | None = None,
    ) -> Dict[str, Any]:
        """
        Process a warehouse query through the MCP-enabled planner graph.

        Args:
            message: User's message/query
            session_id: Session identifier for context
            context: Additional context for the query
            approval_context: Authenticated approval identity for tool execution

        Returns:
            Dictionary containing the response and metadata
        """
        if (
            not session_id
            or not session_id.strip()
            or session_id.casefold() == "default"
        ):
            raise ValueError("A validated non-default session ID is required.")
        if approval_context is not None and (
            approval_context.thread_id != session_id
            or approval_context.checkpoint_ns != CHECKPOINT_NAMESPACE
        ):
            raise _ApprovalWorkflowError(
                "Approval context does not match the workflow checkpoint."
            )

        try:
            # Initialize if needed with timeout
            if not self.initialized:
                try:
                    await asyncio.wait_for(self.initialize(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Initialization timed out, using fallback")
                    return self._create_fallback_response(message, session_id)
                except Exception as init_err:
                    logger.warning(f"Initialization failed: {init_err}, using fallback")
                    return self._create_fallback_response(message, session_id)
            
            if not self.graph:
                logger.warning("Graph not available, using fallback")
                return self._create_fallback_response(message, session_id)

            # Initialize state
            # Extract reasoning parameters from context
            enable_reasoning = context.get("enable_reasoning", False) if context else False
            reasoning_types = context.get("reasoning_types") if context else None
            
            persisted_context = _sanitize_graph_context(context or {})
            initial_state = MCPWarehouseState(
                messages=[HumanMessage(content=message)],
                user_intent=None,
                routing_decision=None,
                routing_confidence=None,
                agent_responses={},
                final_response=None,
                context=persisted_context,
                session_id=session_id,
                mcp_results=None,
                tool_execution_plan=None,
                available_tools=None,
                enable_reasoning=enable_reasoning,
                reasoning_types=reasoning_types,
                reasoning_chain=None,
                planner_scratchpad=None,
                primary_route=None,
                collaboration_plan=None,
                evidence_bundle=None,
                reflection_decision=None,
                reflection_history=[],
                reflection_iterations=0,
                max_reflection_iterations=DEFAULT_MAX_REFLECTION_ITERATIONS,
            )

            # Run the graph asynchronously with timeout
            # Increase timeout when reasoning is enabled (reasoning takes longer)
            # Detect complex queries that need even more time
            message_lower = message.lower()
            is_complex_query = any(keyword in message_lower for keyword in [
                "analyze", "relationship", "between", "compare", "evaluate", 
                "optimize", "calculate", "correlation", "impact", "effect"
            ]) or len(message.split()) > 15
            
            if enable_reasoning:
                # Very complex queries with reasoning need up to 4 minutes
                # Match the timeout in chat.py: 230s for complex, 115s for regular reasoning
                graph_timeout = 230.0 if is_complex_query else 115.0  # 230s for complex, 115s for regular reasoning
            else:
                # Regular queries: Match chat.py timeouts (60s for simple, 90s for complex)
                graph_timeout = 90.0 if is_complex_query else 60.0  # Increased from 30s to 60s for simple queries
            logger.info(f"Graph timeout set to {graph_timeout}s (complex: {is_complex_query}, reasoning: {enable_reasoning})")
            graph_config = {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": CHECKPOINT_NAMESPACE,
                }
            }
            try:
                if approval_context is None:
                    result = await asyncio.wait_for(
                        self.graph.ainvoke(initial_state, config=graph_config),
                        timeout=graph_timeout,
                    )
                else:
                    with bind_approval_context(approval_context):
                        result = await asyncio.wait_for(
                            self.graph.ainvoke(initial_state, config=graph_config),
                            timeout=graph_timeout,
                        )
                logger.info(f"✅ Graph execution completed in time: timeout={graph_timeout}s")
            except RunCancelled as exc:
                await get_run_manager().mark_cancelled(
                    exc.run_id,
                    "图执行观察到取消请求",
                )
                return {
                    "response": "任务已取消。",
                    "intent": "cancelled",
                    "route": "cancelled",
                    "session_id": session_id,
                    "context": {},
                    "execution_status": "cancelled",
                }
            except asyncio.TimeoutError:
                # Sanitize user-controlled message before logging
                safe_message = sanitize_log_data(message, max_length=100)
                logger.error(
                    f"⏱️ TIMEOUT: Graph execution timed out after {graph_timeout}s | "
                    f"Message: {safe_message} | Complex: {is_complex_query} | Reasoning: {enable_reasoning}"
                )
                return self._create_fallback_response(message, session_id)

            return self._format_graph_result(result, session_id)

        except _ApprovalWorkflowError:
            raise
        except Exception as e:
            logger.error(f"Error processing MCP warehouse query: {e}")
            return self._create_fallback_response(message, session_id)

    async def resume_approval(
        self,
        record: ApprovalRecord,
        resume_payload: ApprovalResumePayload,
    ) -> Dict[str, Any]:
        """Resume the existing checkpoint after an approval decision."""
        if (
            not record.thread_id
            or not record.thread_id.strip()
            or record.thread_id.casefold() == "default"
        ):
            raise _ApprovalWorkflowError(
                "Approval record has an invalid workflow thread."
            )
        if record.checkpoint_ns != CHECKPOINT_NAMESPACE:
            raise _ApprovalWorkflowError(
                "Approval record does not match the workflow checkpoint."
            )
        if record.approval_id != resume_payload.approval_id:
            raise _ApprovalWorkflowError(
                "Approval decision does not match the pending approval."
            )
        if self.graph is None:
            raise _ApprovalWorkflowError("Approval workflow is unavailable.")

        approval_context = ApprovalExecutionContext(
            thread_id=record.thread_id,
            checkpoint_ns=record.checkpoint_ns,
            request_id=record.request_id,
            requester_id=record.requester_id,
            requester_username=record.requester_username,
            run_id=record.run_id,
        )
        graph_config = {
            "configurable": {
                "thread_id": record.thread_id,
                "checkpoint_ns": record.checkpoint_ns,
            }
        }

        try:
            if record.run_id is None:
                with bind_approval_context(approval_context):
                    result = await asyncio.wait_for(
                        self.graph.ainvoke(
                            Command(resume=resume_payload.model_dump(mode="json")),
                            config=graph_config,
                        ),
                        timeout=230.0,
                    )
            else:
                run_context = RunExecutionContext(
                    run_id=record.run_id,
                    session_id=record.thread_id,
                    checkpoint_thread_id=record.thread_id,
                    request_id=record.request_id,
                    user_id=record.requester_id,
                    username=record.requester_username,
                    user_role="unknown",
                )
                with bind_run_context(run_context):
                    with bind_approval_context(approval_context):
                        result = await asyncio.wait_for(
                            self.graph.ainvoke(
                                Command(resume=resume_payload.model_dump(mode="json")),
                                config=graph_config,
                            ),
                            timeout=230.0,
                        )
        except asyncio.TimeoutError as exc:
            logger.error(
                "Approval workflow resume timed out for approval %s",
                record.approval_id,
            )
            raise _ApprovalWorkflowError(
                "Approval workflow resume timed out."
            ) from exc

        return self._format_graph_result(result, record.thread_id)
    
    def _create_fallback_response(self, message: str, session_id: str) -> Dict[str, any]:
        """Create a fallback response when MCP graph is unavailable."""
        # Simple intent detection based on keywords
        message_lower = message.lower()
        if any(word in message_lower for word in ["order", "wave", "dispatch", "forklift", "create"]):
            route = "operations"
            intent = "operations"
            response_text = f"I received your request: '{message}'. I understand you want to create a wave and dispatch equipment. The system is processing your request."
        elif any(word in message_lower for word in ["inventory", "stock", "sku", "quantity"]):
            route = "inventory"
            intent = "inventory"
            response_text = f"I received your query: '{message}'. I can help with inventory questions."
        elif any(word in message_lower for word in ["equipment", "asset", "machine"]):
            route = "equipment"
            intent = "equipment"
            response_text = f"I received your question: '{message}'. I can help with equipment information."
        else:
            route = "general"
            intent = "general"
            response_text = f"I received your message: '{message}'. How can I help you?"
        
        return {
            "response": response_text,
            "intent": intent,
            "route": route,
            "session_id": session_id,
            "context": {},
            "structured_response": {
                "natural_language": response_text,
                "data": {},
                "recommendations": [],
                "confidence": 0.6,
            },
            "mcp_tools_used": [],
            "tool_execution_results": {},
            "available_tools": [],
        }


async def _emit_run_event(
    event_type: RunEventType,
    message: str,
    *,
    severity: RunEventSeverity = RunEventSeverity.INFO,
    agent_name: str | None = None,
    tool_name: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a run event when graph execution is bound to a run."""

    context = get_run_context()
    if context is None:
        return
    await get_run_manager().emit_event(
        run_id=context.run_id,
        event_type=event_type,
        message=message,
        severity=severity,
        agent_name=agent_name,
        tool_name=tool_name,
        payload=payload,
    )


async def _emit_reflection_event(decision: Dict[str, Any]) -> None:
    """Append a specialized run event for reflection decisions."""

    action = str(decision.get("action") or "finalize")
    llm_judge = decision.get("llm_judge")
    judge_summary = llm_judge if isinstance(llm_judge, dict) else {}
    if action == "replan":
        event_type = RunEventType.REFLECTION_REPLAN
        message = f"反思要求重规划：下一路由 {decision.get('next_route') or 'general'}"
        severity = RunEventSeverity.WARNING
    elif action == "clarify":
        event_type = RunEventType.REFLECTION_CLARIFICATION_REQUESTED
        message = "反思要求补充信息"
        severity = RunEventSeverity.WARNING
    else:
        event_type = RunEventType.REFLECTION_REVIEWED
        message = "反思检查通过，进入最终汇总"
        severity = RunEventSeverity.INFO

    await _emit_run_event(
        event_type,
        message,
        severity=severity,
        agent_name="reflect",
        payload={
            "action": action,
            "iteration": decision.get("iteration"),
            "max_iterations": decision.get("max_iterations"),
            "route": decision.get("route"),
            "next_route": decision.get("next_route"),
            "confidence": decision.get("confidence"),
            "reasons": decision.get("reasons", []),
            "missing_facts": decision.get("missing_facts", []),
            "judge_status": judge_summary.get("status"),
            "judge_mode": judge_summary.get("mode"),
            "judge_decision": judge_summary.get("decision"),
            "judge_model": judge_summary.get("model"),
            "quality_score": judge_summary.get("quality_score"),
            "route_score": judge_summary.get("route_score"),
            "safety_score": judge_summary.get("safety_score"),
            "judge_confidence": judge_summary.get("confidence"),
            "used_rule_fallback": judge_summary.get("used_rule_fallback"),
            "safety_override_blocked": judge_summary.get("safety_override_blocked"),
        },
    )


async def _update_current_run_risk_level(risk_level: str) -> None:
    """Best-effort run risk update for the Run Center list."""

    context = get_run_context()
    if context is None:
        return
    try:
        await get_run_manager().repository.update_run(
            context.run_id,
            RunUpdate(risk_level=risk_level),
        )
    except Exception as exc:
        logger.warning(
            "Unable to update run risk level for %s: %s",
            context.run_id,
            sanitize_log_data(str(exc)),
        )


async def _check_run_cancelled() -> None:
    """Raise when the current run has requested cancellation."""

    context = get_run_context()
    if context is not None:
        await get_run_manager().ensure_not_cancelled(context.run_id)


# Global MCP planner graph instance
_mcp_planner_graph = None
_mcp_planner_graph_lock = asyncio.Lock()


async def get_mcp_planner_graph() -> MCPPlannerGraph:
    """Get the global MCP planner graph instance."""
    global _mcp_planner_graph
    if _mcp_planner_graph is None:
        async with _mcp_planner_graph_lock:
            if _mcp_planner_graph is None:
                manager = get_checkpoint_manager()
                await manager.start()
                planner_graph = MCPPlannerGraph(checkpointer=manager.saver)
                await planner_graph.initialize()
                _mcp_planner_graph = planner_graph
    return _mcp_planner_graph


def reset_mcp_planner_graph() -> None:
    """Drop the cached MCP planner graph instance."""
    global _mcp_planner_graph
    _mcp_planner_graph = None


async def process_mcp_warehouse_query(
    message: str,
    session_id: str,
    context: Optional[Dict] = None,
    approval_context: ApprovalExecutionContext | None = None,
) -> Dict[str, Any]:
    """
    Process a warehouse query through the MCP-enabled planner graph.

    Args:
        message: User's message/query
        session_id: Session identifier for context
        context: Additional context for the query
        approval_context: Authenticated approval identity for tool execution

    Returns:
        Dictionary containing the response and metadata
    """
    mcp_planner = await get_mcp_planner_graph()
    return await mcp_planner.process_warehouse_query(
        message=message,
        session_id=session_id,
        context=context,
        approval_context=approval_context,
    )


async def resume_expired_approval(record: ApprovalRecord) -> None:
    """Reject and resume an approval that exceeded its validity period."""
    mcp_planner = await get_mcp_planner_graph()
    resume_payload = ApprovalResumePayload(
        approval_id=record.approval_id,
        decision=ApprovalDecision.REJECT,
        approver_id=None,
        approver_username="system-expiry",
        reason="瀹℃壒宸茶秴杩?4灏忔椂鏈夋晥鏈焋",
    )
    await mcp_planner.resume_approval(record, resume_payload)
