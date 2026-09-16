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

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
import time
import logging
import os
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
from src.api.routers.health import router as health_router
from src.api.routers.chat import router as chat_router
from src.api.routers.chat_v2 import router as chat_v2_router
from src.api.routers.execution_v2 import router as execution_v2_router
from src.api.routers.approvals import router as approvals_router
from src.api.routers.runs import router as runs_router
from src.api.routers.equipment import router as equipment_router
from src.api.routers.operations import router as operations_router
from src.api.routers.safety import router as safety_router
from src.api.routers.auth import router as auth_router
from src.api.routers.wms import router as wms_router
from src.api.routers.iot import router as iot_router
from src.api.routers.erp import router as erp_router
from src.api.routers.scanning import router as scanning_router
from src.api.routers.attendance import router as attendance_router
from src.api.routers.reasoning import router as reasoning_router
from src.api.routers.migration import router as migration_router
from src.api.routers.mcp import router as mcp_router
from src.api.routers.document import router as document_router
from src.api.routers.inventory import router as inventory_router
from src.api.routers.advanced_forecasting import router as forecasting_router
from src.api.routers.training import router as training_router
from src.api.services.monitoring.metrics import (
    record_request_metrics,
    get_metrics_response,
)
from src.api.middleware.security_headers import SecurityHeadersMiddleware
from src.api.services.security.rate_limiter import get_rate_limiter
from src.api.services.checkpointing import get_checkpoint_manager
from src.api.services.approval import get_approval_manager
from src.api.services.runs import get_run_manager
from src.api.graphs.mcp_integrated_planner_graph import (
    reset_mcp_planner_graph,
    resume_expired_approval,
)
from src.api.utils.error_handler import (
    handle_validation_error,
    handle_http_exception,
    handle_generic_exception,
)
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting Warehouse Operational Assistant...")

    checkpoint_manager = get_checkpoint_manager()
    approval_manager = get_approval_manager()
    run_manager = get_run_manager()
    v2_worker_task = None
    v2_relay_task = None
    execution_store_manager = None
    memory_store_manager = None
    try:
        await checkpoint_manager.start()
        logger.info(
            "LangGraph checkpoint manager initialized with backend: %s",
            checkpoint_manager.backend,
        )

        await approval_manager.start()
        logger.info(
            "LangGraph approval manager initialized: started=%s",
            approval_manager.started,
        )
        approval_manager.start_expiry_worker(resume_expired_approval)
        logger.info("LangGraph approval expiry worker started")

        await run_manager.start()
        run_manager.start_cleanup_worker()
        logger.info("Agent run manager initialized: started=%s", run_manager.started)

        # V2 is opt-in. When SAP is enabled, wire its existing MCP adapter/BFF
        # into the new constraint-first runtime; otherwise the endpoint reports
        # that providers are not configured instead of simulating success.
        try:
            from src.api.services.feature_flags import FeatureFlags

            feature_flags = FeatureFlags.from_env()
            if feature_flags.agent_runtime_v2_enabled:
                from src.api.routers.chat_v2 import configure_platform_v2
                from src.api.services.mcp.adapters.sap_ewm_adapter import (
                    get_sap_ewm_mcp_adapter,
                )
                from src.api.services.mcp.gateway_v2 import MCPGatewayV2
                from src.api.services.mcp.legacy_adapter_v2 import (
                    register_legacy_adapter,
                )
                from src.api.services.runtime_v2 import (
                    WarehouseAgentPlatformV2,
                    sap_orders_arguments,
                    sap_stock_arguments,
                )
                from src.api.services.execution.control_plane import (
                    ControlledExecutionService,
                )
                from src.api.services.memory_v2.loader import MemoryLoader
                from src.api.services.memory_v2.manager import (
                    get_memory_store_manager,
                )
                from src.api.services.memory_v2.writer import MemoryWriter

                control_plane = None
                memory_loader = None
                memory_writer = None
                try:
                    memory_store_manager = get_memory_store_manager()
                    await memory_store_manager.start()
                    memory_loader = MemoryLoader(memory_store_manager.store)
                    memory_writer = MemoryWriter(memory_store_manager.store)
                    app.state.memory_store_v2 = memory_store_manager.store
                    logger.info(
                        "Memory V2 initialized with backend: %s",
                        memory_store_manager.backend,
                    )
                except Exception as exc:
                    memory_store_manager = None
                    logger.warning(
                        "Memory V2 unavailable; runtime will continue without memory: %s",
                        type(exc).__name__,
                    )
                if feature_flags.execution_v2_enabled:
                    from src.api.services.execution.manager import (
                        get_execution_store_manager,
                    )

                    execution_store_manager = get_execution_store_manager()
                    await execution_store_manager.start()
                    control_plane = ControlledExecutionService(
                        execution_store_manager.store
                    )
                if control_plane is not None:
                    from src.api.routers.execution_v2 import configure_execution_v2

                    configure_execution_v2(control_plane)
                    app.state.execution_control_plane_v2 = control_plane

                sap_adapter = await get_sap_ewm_mcp_adapter()
                if sap_adapter is not None:
                    gateway = MCPGatewayV2()
                    register_legacy_adapter(gateway, sap_adapter)
                    platform = WarehouseAgentPlatformV2(
                        mcp_gateway=gateway,
                        mcp_tool_bindings={
                            "warehouse.fact.query": "sap_ewm_get_physical_stock",
                            "sap.ewm.stock.query": "sap_ewm_get_physical_stock",
                            "sap.ewm.orders.query": "sap_ewm_list_orders_and_tasks",
                        },
                        mcp_argument_builders={
                            "warehouse.fact.query": sap_stock_arguments,
                            "sap.ewm.stock.query": sap_stock_arguments,
                            "sap.ewm.orders.query": sap_orders_arguments,
                        },
                        control_plane=control_plane,
                        memory_loader=memory_loader,
                        memory_writer=memory_writer,
                        checkpointer=checkpoint_manager.saver,
                    )
                    configure_platform_v2(platform)
                    app.state.agent_platform_v2 = platform
                    logger.info("Agent runtime V2 configured with SAP EWM MCP provider")
                    local_worker_enabled = os.getenv(
                        "WAREHOUSE_EXECUTION_LOCAL_WORKER", "false"
                    ).strip().lower() in {"1", "true", "yes", "on"}
                    if control_plane is not None and local_worker_enabled:
                        from src.api.services.execution.sap_handlers import (
                            SAPEWMCommandHandlers,
                        )
                        from src.api.services.execution.worker import CommandWorker

                        worker = CommandWorker(
                            control_plane.store,
                            SAPEWMCommandHandlers(
                                sap_adapter.wms_service,
                                connection_id=sap_adapter.sap_config.connection_id,
                            ).bindings(),
                            evidence_store=platform.evidence_store,
                        )
                        app.state.command_worker_v2 = worker
                        v2_worker_task = asyncio.create_task(
                            _run_local_v2_worker(worker)
                        )
                        logger.info("Execution V2 local worker started")
                    elif control_plane is not None and os.getenv(
                        "WAREHOUSE_EXECUTION_OUTBOX_RELAY", "true"
                    ).strip().lower() in {"1", "true", "yes", "on"}:
                        from src.api.services.execution.celery_app import (
                            CeleryCommandPublisher,
                        )
                        from src.api.services.execution.outbox_relay import OutboxRelay

                        relay = OutboxRelay(
                            control_plane.store, CeleryCommandPublisher()
                        )
                        app.state.outbox_relay_v2 = relay
                        v2_relay_task = asyncio.create_task(_run_outbox_relay_v2(relay))
                        logger.info("Execution V2 Celery outbox relay started")
                else:
                    logger.warning(
                        "Agent runtime V2 enabled but SAP EWM provider is disabled"
                    )
        except Exception as exc:
            logger.error(
                "Agent runtime V2 provider initialization failed: %s",
                type(exc).__name__,
            )

        # Initialize rate limiter (will be initialized on first use if this fails)
        try:
            rate_limiter = await get_rate_limiter()
            logger.info("✅ Rate limiter initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize rate limiter during startup: {e}")
            logger.info("Rate limiter will be initialized on first request")

        # Start alert checker for performance monitoring
        try:
            from src.api.services.monitoring.performance_monitor import (
                get_performance_monitor,
            )
            from src.api.services.monitoring.alert_checker import get_alert_checker

            performance_monitor = get_performance_monitor()
            alert_checker = get_alert_checker(performance_monitor)
            await alert_checker.start()
            logger.info("✅ Alert checker started")
        except Exception as e:
            logger.warning(f"Failed to start alert checker: {e}")

        yield
    finally:
        # Shutdown
        logger.info("Shutting down Warehouse Operational Assistant...")

        if v2_worker_task is not None:
            v2_worker_task.cancel()
            try:
                await v2_worker_task
            except asyncio.CancelledError:
                pass

        if v2_relay_task is not None:
            v2_relay_task.cancel()
            try:
                await v2_relay_task
            except asyncio.CancelledError:
                pass

        if execution_store_manager is not None:
            try:
                await execution_store_manager.close()
                logger.info("Execution V2 store manager stopped")
            except Exception as e:
                logger.warning(
                    "Failed to stop Execution V2 store manager: %s",
                    type(e).__name__,
                )

        if memory_store_manager is not None:
            try:
                await memory_store_manager.close()
                logger.info("Memory V2 store manager stopped")
            except Exception as e:
                logger.warning(
                    "Failed to stop Memory V2 store manager: %s",
                    type(e).__name__,
                )

        try:
            await approval_manager.close()
            logger.info("LangGraph approval manager stopped")
        except Exception as e:
            logger.warning(
                "Failed to stop LangGraph approval manager: %s",
                type(e).__name__,
            )

        try:
            await run_manager.close()
            logger.info("Agent run manager stopped")
        except Exception as e:
            logger.warning(
                "Failed to stop Agent run manager: %s",
                type(e).__name__,
            )

        try:
            reset_mcp_planner_graph()
        except Exception as e:
            logger.warning(
                "Failed to reset LangGraph Planner: %s",
                type(e).__name__,
            )
        try:
            await checkpoint_manager.close()
            logger.info("LangGraph checkpoint manager stopped")
        except Exception as e:
            logger.warning(
                "Failed to stop LangGraph checkpoint manager: %s",
                type(e).__name__,
            )

        # Stop rate limiter
        try:
            rate_limiter = await get_rate_limiter()
            await rate_limiter.close()
            logger.info("✅ Rate limiter stopped")
        except Exception as e:
            logger.warning(f"Failed to stop rate limiter: {e}")

        # Stop alert checker
        try:
            from src.api.services.monitoring.alert_checker import get_alert_checker
            from src.api.services.monitoring.performance_monitor import (
                get_performance_monitor,
            )

            performance_monitor = get_performance_monitor()
            alert_checker = get_alert_checker(performance_monitor)
            await alert_checker.stop()
            logger.info("✅ Alert checker stopped")
        except Exception as e:
            logger.warning(f"Failed to stop alert checker: {e}")


async def _run_local_v2_worker(worker) -> None:
    """Development fallback; production deployments should use an external queue."""

    while True:
        processed = await worker.process_next()
        if processed is None:
            await asyncio.sleep(0.5)


async def _run_outbox_relay_v2(relay) -> None:
    """Relay committed commands; the API process never performs SAP writes."""

    poll_seconds = float(os.getenv("WAREHOUSE_EXECUTION_RELAY_POLL_SECONDS", "0.5"))
    while True:
        report = await relay.publish_batch(limit=100)
        if report.claimed == 0 or report.failed > 0:
            await asyncio.sleep(poll_seconds)


# Request size limits (10MB for JSON, 50MB for file uploads)
def _safe_int_env(key: str, default: int) -> int:
    """Safely parse integer from environment variable, stripping comments."""
    value = os.getenv(key, str(default))
    value = value.split("#")[0].strip()
    try:
        return int(value)
    except ValueError:
        return default


MAX_REQUEST_SIZE = _safe_int_env("MAX_REQUEST_SIZE", 10485760)  # 10MB default
MAX_UPLOAD_SIZE = _safe_int_env("MAX_UPLOAD_SIZE", 52428800)  # 50MB default

app = FastAPI(
    title="Warehouse Operational Assistant",
    version="0.1.0",
    lifespan=lifespan,
    # Request size limits
    max_request_size=MAX_REQUEST_SIZE,
)


# Add exception handlers for secure error handling
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors securely."""
    return await handle_validation_error(request, exc)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions securely."""
    return await handle_http_exception(request, exc)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle generic exceptions securely."""
    # Special handling for circular reference errors (chat endpoint)
    error_msg = str(exc)
    if "circular reference" in error_msg.lower() or "circular" in error_msg.lower():
        logger.error(f"Circular reference error in {request.url.path}: {error_msg}")
        # Return a simple, serializable error response for chat endpoint
        if request.url.path == "/api/v1/chat":
            try:
                return JSONResponse(
                    status_code=200,  # Return 200 so frontend doesn't treat it as an error
                    content={
                        "reply": "I received your request, but there was an issue formatting the response. Please try again with a simpler question.",
                        "route": "error",
                        "intent": "error",
                        "session_id": "default",
                        "confidence": 0.0,
                        "error": "Response serialization failed",
                        "error_type": "circular_reference",
                    },
                )
            except Exception as e:
                logger.error(f"Failed to create error response: {e}")
                # Last resort - return plain text
                return Response(
                    status_code=200,
                    content='{"reply": "Error processing request", "route": "error", "intent": "error", "session_id": "default", "confidence": 0.0}',
                    media_type="application/json",
                )

    # Use generic exception handler for all other exceptions
    return await handle_generic_exception(request, exc)


# CORS Configuration - environment-based for security
# Security: HTTP protocol is acceptable for localhost in development/testing only
# For production deployments, HTTPS must be used to encrypt API communications
# SonarQube may flag HTTP usage, but it's acceptable for:
# - localhost (127.0.0.1, 0.0.0.0) - development/testing only
# Production external services must use HTTPS
cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3001,http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000",
)
cors_origins_list = [
    origin.strip() for origin in cors_origins.split(",") if origin.strip()
]

# Add security headers middleware (must be first)
app.add_middleware(SecurityHeadersMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


# Add rate limiting middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    # Skip rate limiting for health checks and metrics
    if request.url.path in [
        "/health",
        "/api/v1/health",
        "/api/v1/health/simple",
        "/api/v1/metrics",
        "/docs",
        "/openapi.json",
        "/",
    ]:
        return await call_next(request)

    try:
        rate_limiter = await get_rate_limiter()
        # check_rate_limit raises HTTPException if limit exceeded, returns True if allowed
        await rate_limiter.check_rate_limit(request)
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (429 Too Many Requests)
        raise http_exc
    except Exception as e:
        logger.error(f"Rate limiting error: {e}", exc_info=True)
        # Fail open - allow request if rate limiter fails
        pass

    return await call_next(request)


# Add request size limit middleware
@app.middleware("http")
async def request_size_middleware(request: Request, call_next):
    """Check request size limits."""
    # Check content-length header
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            size = int(content_length)
            # Different limits for different endpoints
            if "/document/upload" in request.url.path or "/upload" in request.url.path:
                max_size = MAX_UPLOAD_SIZE
            else:
                max_size = MAX_REQUEST_SIZE

            if size > max_size:
                from fastapi import HTTPException, status

                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Request too large. Maximum size: {max_size / 1024 / 1024:.1f}MB",
                )
        except ValueError:
            # Invalid content-length, let it through (will be caught by FastAPI)
            pass

    return await call_next(request)


# Add metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    record_request_metrics(request, response, duration)
    return response


app.include_router(health_router)
app.include_router(chat_router)
app.include_router(chat_v2_router)
app.include_router(execution_v2_router)
app.include_router(approvals_router)
app.include_router(runs_router)
app.include_router(equipment_router)
app.include_router(operations_router)
app.include_router(safety_router)
app.include_router(auth_router)
app.include_router(wms_router)
app.include_router(iot_router)
app.include_router(erp_router)
app.include_router(scanning_router)
app.include_router(attendance_router)
app.include_router(reasoning_router)
app.include_router(migration_router)
app.include_router(mcp_router)
app.include_router(document_router)
app.include_router(inventory_router)
app.include_router(forecasting_router)
app.include_router(training_router)


@app.get("/")
async def root():
    """Root endpoint providing API information and links."""
    return {
        "name": "Warehouse Operational Assistant API",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/api/v1/health",
        "health_simple": "/api/v1/health/simple",
    }


@app.get("/health")
async def health_check_simple():
    """
    Simple health check endpoint at root level for convenience.

    This endpoint provides a quick health check without the /api/v1 prefix.
    For comprehensive health information, use /api/v1/health instead.
    """
    try:
        # Quick database check
        import asyncpg
        import os
        from dotenv import load_dotenv

        load_dotenv()
        database_url = os.getenv(
            "DATABASE_URL",
            f"postgresql://{os.getenv('POSTGRES_USER', 'warehouse')}:{os.getenv('POSTGRES_PASSWORD', '')}@localhost:5435/{os.getenv('POSTGRES_DB', 'warehouse')}",
        )

        conn = await asyncpg.connect(database_url)
        await conn.execute("SELECT 1")
        await conn.close()

        return {"ok": True, "status": "healthy"}
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        # Don't expose error details in health check
        from src.api.utils.error_handler import sanitize_error_message

        error_msg = sanitize_error_message(e, "Health check")
        return {"ok": False, "status": "unhealthy", "error": error_msg}


# Add metrics endpoint
@app.get("/api/v1/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics_response()
