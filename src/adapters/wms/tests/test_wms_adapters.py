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
Tests for WMS adapters.
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.adapters.wms.base import (
    BaseWMSAdapter, InventoryItem, Task, Order, Location,
    TaskStatus, TaskType, WMSConnectionError, WMSDataError
)
from src.adapters.wms.sap_ewm import SAPEWMAdapter
from src.adapters.wms.sap_ewm_http import SAPEWMODataClient
from src.adapters.wms.manhattan import ManhattanAdapter
from src.adapters.wms.oracle import OracleWMSAdapter
from src.adapters.wms.factory import WMSAdapterFactory
from src.api.services.wms.integration_service import WMSIntegrationService

class TestBaseWMSAdapter:
    """Test base WMS adapter functionality."""
    
    def test_base_adapter_initialization(self):
        """Test base adapter initialization."""
        config = {"test": "value"}
        adapter = BaseWMSAdapter(config)
        
        assert adapter.config == config
        assert adapter.connected == False
        assert adapter.logger is not None
    
    def test_validate_config_success(self):
        """Test successful config validation."""
        config = {"required_field": "value", "optional_field": "value"}
        adapter = BaseWMSAdapter(config)
        
        result = adapter._validate_config(["required_field"])
        assert result == True
    
    def test_validate_config_failure(self):
        """Test failed config validation."""
        config = {"optional_field": "value"}
        adapter = BaseWMSAdapter(config)
        
        result = adapter._validate_config(["required_field"])
        assert result == False
    
    def test_log_operation(self):
        """Test operation logging."""
        config = {"test": "value"}
        adapter = BaseWMSAdapter(config)
        
        # Should not raise any exceptions
        adapter._log_operation("test_operation", {"key": "value"})

class TestSAPEWMAdapter:
    """Test SAP EWM adapter."""
    
    @pytest.fixture
    def sap_config(self):
        """
        Create SAP EWM adapter test configuration.
        
        NOTE: This is a test fixture with mock credentials. The password is a placeholder
        and is never used for actual WMS connections (tests use mocked connections).
        """
        return {
            "enabled": True,
            "mock_mode": True,
            "base_url": "http://test-sap.com",
            "client": "100",
            "auth_mode": "basic",
            "username": "test_user",
            # Test-only placeholder password - never used for real connections
            "password": "<TEST_PASSWORD_PLACEHOLDER>",
            "warehouse": "EW01",
            "verify_tls": False,
        }
    
    @pytest.fixture
    def sap_adapter(self, sap_config):
        return SAPEWMAdapter(sap_config)
    
    def test_sap_adapter_initialization(self, sap_config):
        """Test SAP adapter initialization."""
        adapter = SAPEWMAdapter(sap_config)
        
        assert str(adapter.sap_config.base_url).rstrip("/") == "http://test-sap.com"
        assert adapter.sap_config.username == "test_user"
        assert adapter.sap_config.warehouse == "EW01"
        assert adapter.sap_config.mock_mode is True
    
    @pytest.mark.asyncio
    async def test_sap_adapter_connect_rest(self, sap_adapter):
        """Test SAP adapter REST connection."""
        client = AsyncMock(spec=SAPEWMODataClient)
        client.connect.return_value = True
        adapter = SAPEWMAdapter(sap_adapter.sap_config, client=client)

        result = await adapter.connect()

        assert result is True
        assert adapter.connected is True
        client.connect.assert_awaited_once()
    
    def test_sap_task_status_mapping(self, sap_adapter):
        """Test SAP task status mapping."""
        # Test internal to SAP mapping
        assert sap_adapter._map_task_status_to_sap(TaskStatus.PENDING) == "P"
        assert sap_adapter._map_task_status_to_sap(TaskStatus.COMPLETED) == "C"
        
        # Test SAP to internal mapping
        assert sap_adapter._map_sap_task_status("P") == TaskStatus.PENDING
        assert sap_adapter._map_sap_task_status("C") == TaskStatus.COMPLETED
    
    def test_sap_task_type_mapping(self, sap_adapter):
        """Test SAP task type mapping."""
        # Test internal to SAP mapping
        assert sap_adapter._map_task_type_to_sap(TaskType.PICK) == "PICK"
        assert sap_adapter._map_task_type_to_sap(TaskType.PACK) == "PACK"
        
        # Test SAP to internal mapping
        assert sap_adapter._map_sap_task_type("PICK") == TaskType.PICK
        assert sap_adapter._map_sap_task_type("PACK") == TaskType.PACK

class TestManhattanAdapter:
    """Test Manhattan WMS adapter."""
    
    @pytest.fixture
    def manhattan_config(self):
        """
        Create Manhattan WMS adapter test configuration.
        
        NOTE: This is a test fixture with mock credentials. The password is a placeholder
        and is never used for actual WMS connections (tests use mocked connections).
        """
        return {
            "host": "test-manhattan.com",
            "username": "test_user",
            # Test-only placeholder password - never used for real connections
            "password": "<TEST_PASSWORD_PLACEHOLDER>",
            "facility_id": "FAC001"
        }
    
    @pytest.fixture
    def manhattan_adapter(self, manhattan_config):
        return ManhattanAdapter(manhattan_config)
    
    def test_manhattan_adapter_initialization(self, manhattan_config):
        """Test Manhattan adapter initialization."""
        adapter = ManhattanAdapter(manhattan_config)
        
        assert adapter.host == "test-manhattan.com"
        assert adapter.username == "test_user"
        assert adapter.facility_id == "FAC001"
        assert adapter.use_ssl == True
    
    @pytest.mark.asyncio
    async def test_manhattan_adapter_authenticate(self, manhattan_adapter):
        """Test Manhattan adapter authentication."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"token": "test_token"}
            mock_client.return_value.post.return_value = mock_response
            
            result = await manhattan_adapter._authenticate()
            assert result == True
            assert manhattan_adapter.auth_token == "test_token"
            assert manhattan_adapter.connected == True

class TestOracleAdapter:
    """Test Oracle WMS adapter."""
    
    @pytest.fixture
    def oracle_config(self):
        """
        Create Oracle WMS adapter test configuration.
        
        NOTE: This is a test fixture with mock credentials. The password is a placeholder
        and is never used for actual WMS connections (tests use mocked connections).
        """
        return {
            "host": "test-oracle.com",
            "username": "test_user",
            # Test-only placeholder password - never used for real connections
            "password": "<TEST_PASSWORD_PLACEHOLDER>",
            "organization_id": "ORG001"
        }
    
    @pytest.fixture
    def oracle_adapter(self, oracle_config):
        return OracleWMSAdapter(oracle_config)
    
    def test_oracle_adapter_initialization(self, oracle_config):
        """Test Oracle adapter initialization."""
        adapter = OracleWMSAdapter(oracle_config)
        
        assert adapter.host == "test-oracle.com"
        assert adapter.username == "test_user"
        assert adapter.organization_id == "ORG001"
        assert adapter.use_ssl == True

class TestWMSAdapterFactory:
    """Test WMS adapter factory."""
    
    def test_factory_registration(self):
        """Test adapter registration."""
        # Test that default adapters are registered
        adapters = WMSAdapterFactory.list_adapters()
        assert "sap_ewm" in adapters
        assert "manhattan" in adapters
        assert "oracle" in adapters
    
    def test_factory_create_adapter(self):
        """
        Test adapter creation.
        
        NOTE: This test uses mock credentials. The password is a placeholder
        and is never used for actual WMS connections.
        """
        config = {
            "enabled": True,
            "mock_mode": True,
            "base_url": "http://test.com",
            "auth_mode": "basic",
            "username": "test",
            # Test-only placeholder password - never used for real connections
            "password": "<TEST_PASSWORD_PLACEHOLDER>",
            "warehouse": "EW01",
            "verify_tls": False,
        }
        
        adapter = WMSAdapterFactory.create_adapter("sap_ewm", config)
        assert isinstance(adapter, SAPEWMAdapter)
        assert adapter.sap_config.warehouse == "EW01"
    
    def test_factory_create_invalid_adapter(self):
        """Test creating invalid adapter type."""
        with pytest.raises(ValueError):
            WMSAdapterFactory.create_adapter("invalid_type", {})

class TestWMSIntegrationService:
    """Test WMS integration service."""
    
    @pytest.fixture
    def wms_service(self):
        return WMSIntegrationService()
    
    @pytest.fixture
    def mock_adapter(self):
        adapter = Mock(spec=BaseWMSAdapter)
        adapter.connected = True
        adapter.connect = AsyncMock(return_value=True)
        adapter.disconnect = AsyncMock(return_value=True)
        adapter.health_check = AsyncMock(return_value={"status": "healthy"})
        return adapter
    
    @pytest.mark.asyncio
    async def test_add_wms_connection(self, wms_service, mock_adapter):
        """Test adding WMS connection."""
        with patch('adapters.wms.factory.WMSAdapterFactory.create_adapter') as mock_factory:
            mock_factory.return_value = mock_adapter
            
            result = await wms_service.add_wms_connection(
                "sap_ewm", 
                {"test": "config"}, 
                "test_connection"
            )
            
            assert result == True
            assert "test_connection" in wms_service.adapters
    
    @pytest.mark.asyncio
    async def test_remove_wms_connection(self, wms_service, mock_adapter):
        """Test removing WMS connection."""
        wms_service.adapters["test_connection"] = mock_adapter
        
        result = await wms_service.remove_wms_connection("test_connection")
        
        assert result == True
        assert "test_connection" not in wms_service.adapters
    
    @pytest.mark.asyncio
    async def test_get_connection_status(self, wms_service, mock_adapter):
        """Test getting connection status."""
        wms_service.adapters["test_connection"] = mock_adapter
        
        status = await wms_service.get_connection_status("test_connection")
        
        assert status["status"] == "healthy"
        mock_adapter.health_check.assert_called_once()
    
    def test_list_connections(self, wms_service, mock_adapter):
        """Test listing connections."""
        wms_service.adapters["test_connection"] = mock_adapter
        
        connections = wms_service.list_connections()
        
        assert len(connections) == 1
        assert connections[0]["connection_id"] == "test_connection"

class TestDataStructures:
    """Test WMS data structures."""
    
    def test_inventory_item(self):
        """Test inventory item creation."""
        item = InventoryItem(
            sku="TEST001",
            name="Test Item",
            quantity=100,
            location="A1-B2-C3"
        )
        
        assert item.sku == "TEST001"
        assert item.name == "Test Item"
        assert item.quantity == 100
        assert item.location == "A1-B2-C3"
    
    def test_task(self):
        """Test task creation."""
        task = Task(
            task_id="TASK001",
            task_type=TaskType.PICK,
            priority=1,
            status=TaskStatus.PENDING
        )
        
        assert task.task_id == "TASK001"
        assert task.task_type == TaskType.PICK
        assert task.priority == 1
        assert task.status == TaskStatus.PENDING
    
    def test_order(self):
        """Test order creation."""
        order = Order(
            order_id="ORDER001",
            order_type="SALES",
            status="PENDING"
        )
        
        assert order.order_id == "ORDER001"
        assert order.order_type == "SALES"
        assert order.status == "PENDING"
    
    def test_location(self):
        """Test location creation."""
        location = Location(
            location_id="LOC001",
            name="Test Location",
            zone="ZONE_A"
        )
        
        assert location.location_id == "LOC001"
        assert location.name == "Test Location"
        assert location.zone == "ZONE_A"

if __name__ == "__main__":
    pytest.main([__file__])
