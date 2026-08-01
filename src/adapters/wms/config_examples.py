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
WMS Configuration Examples.

Provides example configurations for different WMS systems
to help with setup and integration.
"""

# SAP EWM Configuration Example
SAP_EWM_CONFIG = {
    "enabled": True,
    "connection_id": "sap-ewm-default",
    "mock_mode": False,
    "base_url": "https://sap-ewm.company.com",
    "client": "100",
    "auth_mode": "basic",
    "username": "WMS_USER",
    "password": "secure_password",
    "warehouse": "EW01",
    "verify_tls": True,
    "connect_timeout_seconds": 5,
    "read_timeout_seconds": 15,
    "max_read_attempts": 3,
}

# Manhattan WMS Configuration Example
MANHATTAN_CONFIG = {
    "host": "manhattan-wms.company.com",
    "port": 8080,
    "username": "wms_user",
    "password": "secure_password",
    "facility_id": "FAC001",
    "client_id": "CLIENT001",
    "use_ssl": True
}

# Oracle WMS Configuration Example
ORACLE_CONFIG = {
    "host": "oracle-wms.company.com",
    "port": 8000,
    "username": "wms_user",
    "password": "secure_password",
    "organization_id": "ORG001",
    "warehouse_id": "WH001",
    "use_ssl": True,
    "database_config": {
        "host": "oracle-db.company.com",
        "port": 1521,
        "service_name": "WMS",
        "username": "wms_db_user",
        "password": "db_password"
    }
}

# Configuration validation schemas
WMS_CONFIG_SCHEMAS = {
    "sap_ewm": {
        "required": ["base_url", "warehouse", "auth_mode"],
        "optional": [
            "enabled",
            "connection_id",
            "mock_mode",
            "client",
            "username",
            "password",
            "token_url",
            "client_id",
            "client_secret",
            "scope",
            "verify_tls",
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "max_read_attempts",
        ],
        "defaults": {
            "enabled": False,
            "connection_id": "sap-ewm-default",
            "mock_mode": False,
            "client": "100",
            "verify_tls": True,
            "connect_timeout_seconds": 5,
            "read_timeout_seconds": 15,
            "max_read_attempts": 3,
        },
    },
    "manhattan": {
        "required": ["host", "username", "password", "facility_id"],
        "optional": ["port", "client_id", "use_ssl"],
        "defaults": {
            "port": 8080,
            "use_ssl": True
        }
    },
    "oracle": {
        "required": ["host", "username", "password", "organization_id"],
        "optional": ["port", "warehouse_id", "use_ssl", "database_config"],
        "defaults": {
            "port": 8000,
            "use_ssl": True
        }
    }
}

def validate_wms_config(wms_type: str, config: dict) -> tuple[bool, list[str]]:
    """
    Validate WMS configuration.
    
    Args:
        wms_type: Type of WMS system
        config: Configuration dictionary
        
    Returns:
        tuple: (is_valid, error_messages)
    """
    if wms_type not in WMS_CONFIG_SCHEMAS:
        return False, [f"Unsupported WMS type: {wms_type}"]
    
    schema = WMS_CONFIG_SCHEMAS[wms_type]
    errors = []
    
    # Check required fields
    for field in schema["required"]:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Apply defaults
    for field, default_value in schema["defaults"].items():
        if field not in config:
            config[field] = default_value
    
    return len(errors) == 0, errors

def get_config_example(wms_type: str) -> dict:
    """
    Get configuration example for WMS type.
    
    Args:
        wms_type: Type of WMS system
        
    Returns:
        dict: Example configuration
    """
    examples = {
        "sap_ewm": SAP_EWM_CONFIG,
        "manhattan": MANHATTAN_CONFIG,
        "oracle": ORACLE_CONFIG
    }
    
    return examples.get(wms_type, {})
