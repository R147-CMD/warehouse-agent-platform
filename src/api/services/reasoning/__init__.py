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
Reasoning Services for Warehouse Operational Assistant

Provides advanced reasoning capabilities including:
- Chain-of-Thought Reasoning
- Multi-Hop Reasoning
- Scenario Analysis
- Causal Reasoning
- Pattern Recognition
"""

from .reasoning_engine import (
    AdvancedReasoningEngine,
    ReasoningType,
    ReasoningStep,
    ReasoningChain,
    PatternInsight,
    CausalRelationship,
    get_reasoning_engine,
)
from .reflection_loop import (
    DEFAULT_MAX_REFLECTION_ITERATIONS,
    build_planner_decision,
    review_agent_outcome,
    review_agent_outcome_with_judge,
)
from .evidence_join import (
    build_collaboration_plan,
    join_agent_evidence,
    summarize_agent_evidence,
)

__all__ = [
    "AdvancedReasoningEngine",
    "ReasoningType",
    "ReasoningStep",
    "ReasoningChain",
    "PatternInsight",
    "CausalRelationship",
    "get_reasoning_engine",
    "DEFAULT_MAX_REFLECTION_ITERATIONS",
    "build_planner_decision",
    "review_agent_outcome",
    "review_agent_outcome_with_judge",
    "build_collaboration_plan",
    "join_agent_evidence",
    "summarize_agent_evidence",
]
