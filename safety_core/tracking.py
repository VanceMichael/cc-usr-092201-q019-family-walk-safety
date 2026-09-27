"""检查点登记与离线合并。

各检查点设备离线时照常登记，记录自带真实发生时间；
联网后按 event_id 去重、按发生时间排序合并，里程只计一次。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from .models import CheckpointEvent, CheckpointEventKind, Course


@dataclass(frozen=True)
class FamilyProgress:
    """一个家庭在赛道上合并后的进度。"""

    family_id: str
    last_checkpoint_id: str | None
    last_confirmed_at: datetime | None
    distance_km: float
    current_group: str | None
    exited: bool
    finished: bool
    under_medical_observation: bool


class CheckpointLog:
    """检查点登记簿，支持离线记录后的重复合并。"""

    def __init__(self, course: Course) -> None:
        self._course = course
        self._events: dict[str, CheckpointEvent] = {}

    def record(self, event: CheckpointEvent) -> None:
        """登记一条记录；同一 event_id 重复上报只保留一条。"""
        if not self._course.has(event.checkpoint_id):
            raise ValueError(f"未知检查点: {event.checkpoint_id}")
        if event.kind == CheckpointEventKind.临时转组 and not event.to_group:
            raise ValueError("临时转组必须注明目标组别")
        self._events.setdefault(event.event_id, event)

    def merge(self, events: Iterable[CheckpointEvent]) -> list[CheckpointEvent]:
        """联网后合并离线记录，返回新入库的记录；重复记录不会重复计程。"""
        added = []
        for event in events:
            if event.event_id not in self._events:
                self.record(event)
                added.append(event)
        return added

    def events_of(self, family_id: str) -> list[CheckpointEvent]:
        """按真实发生时间返回该家庭的全部记录。"""
        return sorted(
            (e for e in self._events.values() if e.family_id == family_id),
            key=lambda e: (e.occurred_at, e.event_id),
        )

    def progress(self, family_id: str, *, base_group: str | None = None) -> FamilyProgress:
        """由合并后的记录推导家庭进度，与记录上传顺序无关。"""
        last_checkpoint_id = None
        last_confirmed_at = None
        distance = 0.0
        current_group = base_group
        exited = False
        finished = False
        under_medical = False
        for event in self.events_of(family_id):
            if event.kind in (CheckpointEventKind.到达, CheckpointEventKind.终点核销):
                last_checkpoint_id = event.checkpoint_id
                last_confirmed_at = event.occurred_at
                distance = max(distance, self._course.distance_of(event.checkpoint_id))
                under_medical = False
                exited = False
                if event.kind == CheckpointEventKind.终点核销:
                    finished = True
            elif event.kind == CheckpointEventKind.医疗观察:
                under_medical = True
            elif event.kind == CheckpointEventKind.退出:
                exited = True
            elif event.kind == CheckpointEventKind.临时转组:
                current_group = event.to_group
        return FamilyProgress(
            family_id=family_id,
            last_checkpoint_id=last_checkpoint_id,
            last_confirmed_at=last_confirmed_at,
            distance_km=distance,
            current_group=current_group,
            exited=exited,
            finished=finished,
            under_medical_observation=under_medical,
        )
