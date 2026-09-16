from __future__ import annotations

from xml.etree import ElementTree

from fastapi.testclient import TestClient

from src.mock_servers.sap_ewm.app import ORDER_ROOT, create_app

EDM = "{http://docs.oasis-open.org/odata/ns/edm}"


def test_order_metadata_declares_mapped_entities_and_bound_write_actions() -> None:
    with TestClient(create_app(control_enabled=False)) as client:
        response = client.get(
            ORDER_ROOT + "/$metadata", auth=("mock-user", "mock-password")
        )

    root = ElementTree.fromstring(response.text)
    schema = root.find(f".//{EDM}Schema")
    assert schema is not None
    assert schema.attrib["Alias"] == "SAP__self"

    entities = {
        item.attrib["Name"]: {
            prop.attrib["Name"] for prop in item.findall(f"{EDM}Property")
        }
        for item in schema.findall(f"{EDM}EntityType")
    }
    assert {
        "EWMWarehouse",
        "WarehouseOrder",
        "WarehouseOrderStatus",
        "ExecutingResource",
    }.issubset(entities["WarehouseOrder"])
    assert {
        "EWMWarehouse",
        "WarehouseTask",
        "WarehouseTaskItem",
        "WarehouseTaskStatus",
    }.issubset(entities["WarehouseTask"])

    actions = {
        item.attrib["Name"]: [
            parameter.attrib["Name"] for parameter in item.findall(f"{EDM}Parameter")
        ]
        for item in schema.findall(f"{EDM}Action")
    }
    assert actions == {
        "AssignWarehouseOrder": ["binding", "EWMResource"],
        "ConfirmWarehouseTaskExact": ["binding"],
    }
