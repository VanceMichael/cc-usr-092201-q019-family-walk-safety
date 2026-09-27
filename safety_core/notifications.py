"""发给家长的联络结果。"""

from __future__ import annotations

from datetime import datetime

from .models import Notification


class NotificationLog:
    """家长联络台账：每条都是明确的联络结果，可回查。"""

    def __init__(self) -> None:
        self._notifications: list[Notification] = []
        self._seq = 0

    def notify(self, family_id: str, *, result: str, now: datetime) -> Notification:
        self._seq += 1
        notification = Notification(
            notification_id=f"MSG-{self._seq:04d}",
            family_id=family_id,
            created_at=now,
            result=result,
        )
        self._notifications.append(notification)
        return notification

    def for_family(self, family_id: str) -> list[Notification]:
        return [n for n in self._notifications if n.family_id == family_id]
