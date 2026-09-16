"""Command handlers that keep SAP side effects outside the LangGraph process."""

from __future__ import annotations

from src.api.services.wms.integration_service import WMSIntegrationService

from .models import Command
from .worker import ExecutionOutcome


class SAPEWMCommandHandlers:
    def __init__(
        self,
        service: WMSIntegrationService,
        *,
        connection_id: str | None = None,
    ) -> None:
        self.service = service
        self.connection_id = connection_id

    def bindings(self):
        return {
            "sap.ewm.order.assign": self.assign_order,
            "sap.ewm.task.confirm": self.confirm_task,
        }

    def readback_bindings(self):
        return {
            "sap.ewm.order.assign": self.readback_order_assignment,
            "sap.ewm.task.confirm": self.readback_task_confirmation,
        }

    async def assign_order(self, command: Command) -> ExecutionOutcome:
        submitted = await self.service.execute(
            command, connection_id=self.connection_id
        )
        verified = await self.service.read_back(
            command, connection_id=self.connection_id
        )
        return ExecutionOutcome(
            accepted=submitted.accepted,
            verified=verified.verified,
            external_reference=verified.external_reference,
            readback=verified.data,
        )

    async def confirm_task(self, command: Command) -> ExecutionOutcome:
        submitted = await self.service.execute(
            command, connection_id=self.connection_id
        )
        verified = await self.service.read_back(
            command, connection_id=self.connection_id
        )
        return ExecutionOutcome(
            accepted=submitted.accepted,
            verified=verified.verified,
            external_reference=verified.external_reference,
            readback=verified.data,
        )

    async def readback_order_assignment(self, command: Command) -> ExecutionOutcome:
        verified = await self.service.read_back(
            command, connection_id=self.connection_id
        )
        return ExecutionOutcome(
            accepted=True,
            verified=verified.verified,
            external_reference=verified.external_reference,
            readback=verified.data,
        )

    async def readback_task_confirmation(self, command: Command) -> ExecutionOutcome:
        verified = await self.service.read_back(
            command, connection_id=self.connection_id
        )
        return ExecutionOutcome(
            accepted=True,
            verified=verified.verified,
            external_reference=verified.external_reference,
            readback=verified.data,
        )
