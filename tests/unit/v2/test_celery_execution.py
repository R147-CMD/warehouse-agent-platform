from __future__ import annotations

from src.api.services.execution.celery_app import CeleryCommandPublisher


class FakeCelery:
    def __init__(self) -> None:
        self.calls = []

    def send_task(self, name, *, args, task_id, queue, headers):
        self.calls.append(
            {
                "name": name,
                "args": args,
                "task_id": task_id,
                "queue": queue,
                "headers": headers,
            }
        )


def test_celery_publisher_uses_event_id_as_delivery_identity() -> None:
    celery = FakeCelery()
    publisher = CeleryCommandPublisher(celery, queue="warehouse.commands")

    publisher("event-1", "command-1")

    assert celery.calls == [
        {
            "name": "warehouse.execution.execute_command",
            "args": ["command-1"],
            "task_id": "event-1",
            "queue": "warehouse.commands",
            "headers": {"outbox_event_id": "event-1"},
        }
    ]
