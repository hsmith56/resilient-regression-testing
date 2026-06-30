from __future__ import annotations

from .client import MockSoarClient


def cleanup_created_incidents(client: MockSoarClient) -> list[int]:
    return client.cleanup_created_incidents()
