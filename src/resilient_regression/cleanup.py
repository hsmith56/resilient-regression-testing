from __future__ import annotations

from .client import BaseSoarClient


def cleanup_created_incidents(client: BaseSoarClient) -> list[int]:
    return client.cleanup_created_incidents()
