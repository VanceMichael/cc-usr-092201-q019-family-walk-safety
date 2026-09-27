"""闭赛把关：全部人员完成安全交接才允许闭赛。"""

from __future__ import annotations

from dataclasses import dataclass

from .incidents import IncidentDesk
from .models import Family


@dataclass(frozen=True)
class CloseReadiness:
    """闭赛条件核对结果，附未就绪原因。"""

    can_close: bool
    pending_families: tuple[str, ...]
    unresolved_incidents: tuple[str, ...]


def close_readiness(
    *,
    families: list[Family],
    handed_over_ids: set[str],
    desk: IncidentDesk,
) -> CloseReadiness:
    """核对闭赛条件：已出发家庭全部完成交接，且没有未解决事件。

    只看终点核销数字不够——核销不等于交接确认；
    已出发的每一户都要有交接确认，才允许闭赛。
    """
    pending = tuple(
        family.family_id
        for family in families
        if family.departed_at is not None and family.family_id not in handed_over_ids
    )
    unresolved = tuple(incident.incident_id for incident in desk.unresolved())
    return CloseReadiness(
        can_close=not pending and not unresolved,
        pending_families=pending,
        unresolved_incidents=unresolved,
    )
