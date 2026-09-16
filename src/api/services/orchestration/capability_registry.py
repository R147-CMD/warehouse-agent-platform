"""Versioned capability registry with hard constraint filtering."""

from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.api.domain.identity import IdentityContext


class CapabilityDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str = Field(min_length=1, max_length=200)
    owner_type: Literal["agent", "service", "tool"]
    owner_id: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    input_schema_ref: str = Field(min_length=1, max_length=200)
    output_schema_ref: str = Field(min_length=1, max_length=200)
    required_scopes: tuple[str, ...] = ()
    supported_tenants: tuple[str, ...] = ()
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    read_write_mode: Literal["read", "propose", "write"] = "read"
    health_status: Literal["available", "degraded", "unavailable"] = "available"
    priority: int = Field(default=100, ge=0, le=1000)
    latency_class: Literal["low", "medium", "high"] = "medium"
    cost_class: Literal["low", "medium", "high"] = "low"
    version: str = Field(min_length=1, max_length=64)


class CapabilityRegistry:
    """Store capability providers and apply non-negotiable eligibility rules."""

    def __init__(self, descriptors: Iterable[CapabilityDescriptor] = ()) -> None:
        self._descriptors: list[CapabilityDescriptor] = []
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        key = (descriptor.capability_id, descriptor.owner_id, descriptor.version)
        if any(
            (item.capability_id, item.owner_id, item.version) == key
            for item in self._descriptors
        ):
            raise ValueError(f"duplicate capability registration: {key}")
        self._descriptors.append(descriptor)

    def resolve(
        self,
        capability_id: str,
        identity: IdentityContext,
    ) -> list[CapabilityDescriptor]:
        user_scopes = set(identity.scopes)
        eligible = [
            descriptor
            for descriptor in self._descriptors
            if descriptor.capability_id == capability_id
            and descriptor.health_status != "unavailable"
            and (
                not descriptor.supported_tenants
                or identity.tenant_id in descriptor.supported_tenants
            )
            and set(descriptor.required_scopes).issubset(user_scopes)
        ]
        return sorted(
            eligible,
            key=lambda item: (-item.priority, item.owner_id, item.version),
        )

    def all(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._descriptors)


def build_default_capability_registry() -> CapabilityRegistry:
    """Return the minimal built-in providers required by V2 planning."""

    definitions = (
        (
            "warehouse.fact.query",
            "operations-agent-v2",
            "Query current warehouse facts",
            ("inventory.read",),
            "read",
            "low",
        ),
        (
            "knowledge.search",
            "document-agent-v2",
            "Search governed warehouse knowledge",
            ("document.read",),
            "read",
            "low",
        ),
        (
            "warehouse.tasks.query",
            "operations-agent-v2",
            "Query warehouse tasks",
            ("operations.read",),
            "read",
            "low",
        ),
        (
            "workforce.availability.query",
            "operations-agent-v2",
            "Query available qualified workers",
            ("operations.read",),
            "read",
            "low",
        ),
        (
            "warehouse.tasks.rebalance.propose",
            "operations-agent-v2",
            "Build a task rebalance proposal",
            ("operations.propose",),
            "propose",
            "medium",
        ),
        (
            "warehouse.action.propose",
            "operations-agent-v2",
            "Build a controlled warehouse action proposal",
            ("operations.propose",),
            "propose",
            "high",
        ),
        (
            "warehouse.wave.propose",
            "operations-agent-v2",
            "Build a picking wave proposal",
            ("operations.propose",),
            "propose",
            "medium",
        ),
        (
            "warehouse.route.optimize",
            "operations-agent-v2",
            "Optimize a picking route",
            ("operations.read",),
            "read",
            "low",
        ),
        (
            "warehouse.dock.schedule.propose",
            "operations-agent-v2",
            "Build a dock schedule proposal",
            ("operations.propose",),
            "propose",
            "medium",
        ),
        (
            "warehouse.shift.plan.propose",
            "operations-agent-v2",
            "Build a shift plan proposal",
            ("operations.propose",),
            "propose",
            "medium",
        ),
        (
            "warehouse.kpi.publish.propose",
            "operations-agent-v2",
            "Build a KPI publication proposal",
            ("operations.propose",),
            "propose",
            "medium",
        ),
        (
            "sap.ewm.stock.query",
            "operations-agent-v2",
            "Query SAP EWM stock",
            ("inventory.read",),
            "read",
            "low",
        ),
        (
            "sap.ewm.orders.query",
            "operations-agent-v2",
            "Query SAP EWM orders and tasks",
            ("operations.read",),
            "read",
            "low",
        ),
        (
            "sap.ewm.order.assign.propose",
            "operations-agent-v2",
            "Propose SAP warehouse order assignment",
            ("sap.order.assign",),
            "propose",
            "high",
        ),
        (
            "sap.ewm.task.confirm.propose",
            "operations-agent-v2",
            "Propose SAP warehouse task confirmation",
            ("sap.task.confirm",),
            "propose",
            "high",
        ),
        (
            "equipment.status.query",
            "equipment-agent-v2",
            "Query equipment status",
            ("equipment.read",),
            "read",
            "low",
        ),
        (
            "equipment.telemetry.query",
            "equipment-agent-v2",
            "Query equipment telemetry",
            ("equipment.read",),
            "read",
            "low",
        ),
        (
            "equipment.maintenance.analyze",
            "equipment-agent-v2",
            "Analyze equipment maintenance",
            ("equipment.read",),
            "read",
            "low",
        ),
        (
            "equipment.dispatch.propose",
            "equipment-agent-v2",
            "Propose equipment dispatch",
            ("equipment.dispatch",),
            "propose",
            "high",
        ),
        (
            "safety.incident.query",
            "safety-agent-v2",
            "Query safety incidents",
            ("safety.read",),
            "read",
            "low",
        ),
        (
            "safety.risk.analyze",
            "safety-agent-v2",
            "Analyze warehouse safety risk",
            ("safety.read",),
            "read",
            "low",
        ),
        (
            "safety.sop.query",
            "safety-agent-v2",
            "Retrieve an approved safety SOP",
            ("safety.read",),
            "read",
            "low",
        ),
        (
            "safety.emergency.plan",
            "safety-agent-v2",
            "Build a rules-preserving emergency plan",
            ("safety.read",),
            "read",
            "high",
        ),
        (
            "forecast.demand.run",
            "forecasting-agent-v2",
            "Run demand forecast service",
            ("forecast.read",),
            "read",
            "low",
        ),
        (
            "forecast.capacity.run",
            "forecasting-agent-v2",
            "Run capacity forecast service",
            ("forecast.read",),
            "read",
            "low",
        ),
        (
            "forecast.workforce.run",
            "forecasting-agent-v2",
            "Run workforce forecast service",
            ("forecast.read",),
            "read",
            "low",
        ),
        (
            "document.extract",
            "document-agent-v2",
            "Parse and extract a warehouse document",
            ("document.write",),
            "propose",
            "medium",
        ),
        (
            "document.index.status",
            "document-agent-v2",
            "Query document indexing status",
            ("document.read",),
            "read",
            "low",
        ),
    )
    return CapabilityRegistry(
        CapabilityDescriptor(
            capability_id=capability_id,
            owner_type="agent",
            owner_id=owner_id,
            description=description,
            input_schema_ref="AgentTask@1.0",
            output_schema_ref="AgentResult@1.0",
            required_scopes=required_scopes,
            risk_level=risk_level,
            read_write_mode=read_write_mode,
            version="1.0.0",
        )
        for (
            capability_id,
            owner_id,
            description,
            required_scopes,
            read_write_mode,
            risk_level,
        ) in definitions
    )
