"""位置等敏感信息的可见性控制。

只有负责岗位（指挥席、检查点工作人员、医疗岗位）以及本家庭成员
可以查看家庭的最后确认点与状态；其他角色一律不可见。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import FamilyStatus, StaffRole
from .service import RaceService

RESPONSIBLE_ROLES = {StaffRole.COMMAND, StaffRole.CHECKPOINT, StaffRole.MEDICAL}


@dataclass(frozen=True)
class Viewer:
    """查看者：工作人员带岗位角色，家长用 family_id 标识本人家庭。"""

    role: StaffRole | None = None
    family_id: str | None = None


@dataclass(frozen=True)
class LocationView:
    family_id: str
    family: str
    batch_id: str | None
    status: FamilyStatus
    last_checkpoint: str | None
    distance_km: float
    awaiting_handover: bool


def location_view(service: RaceService, family_id: str, viewer: Viewer) -> LocationView | None:
    """按角色返回位置视图；无权查看时返回 None。"""
    fam = service.families.get(family_id)
    if fam is None:
        raise ValueError(f"未知家庭：{family_id}")
    is_responsible_staff = viewer.role in RESPONSIBLE_ROLES
    is_own_family = viewer.family_id is not None and viewer.family_id == family_id
    if not (is_responsible_staff or is_own_family):
        return None
    cp = service.last_confirmed_checkpoint(family_id)
    return LocationView(
        family_id=fam.family_id,
        family=fam.name,
        batch_id=fam.current_batch_id,
        status=fam.status,
        last_checkpoint=cp.name if cp else None,
        distance_km=cp.distance_km if cp else 0.0,
        awaiting_handover=fam.awaiting_handover,
    )
