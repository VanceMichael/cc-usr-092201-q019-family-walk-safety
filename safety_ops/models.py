"""亲子健走安全联络后台的领域模型。

记录类型与流程状态沿用 ``fixtures/domain.json`` 的公开约定：
参赛家庭、监护授权、出发批次、检查点记录、安全事件、交接确认；
待核验 → 已出发 → 行进中 → 需协助 → 已交接 → 已闭赛。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FamilyStatus(str, Enum):
    """家庭在赛事中的流程状态。"""

    PENDING = "待核验"
    DEPARTED = "已出发"
    ON_COURSE = "行进中"
    NEEDS_ASSISTANCE = "需协助"
    HANDED_OVER = "已交接"


class EventStatus(str, Enum):
    """赛事整体状态；只有全部人员完成安全交接才允许闭赛。"""

    RUNNING = "进行中"
    CLOSED = "已闭赛"


class MemberRole(str, Enum):
    CHILD = "儿童"
    GUARDIAN = "监护人"
    BACKUP_GUARDIAN = "备用监护人"


class RecordKind(str, Enum):
    """检查点记录类型，对应领域资料中的“检查点记录”。"""

    ARRIVAL = "到达"
    WITHDRAWAL = "退出"
    TRANSFER = "临时转组"
    MEDICAL_OBSERVATION = "医疗观察"
    CHECKOUT = "终点核销"


class IncidentType(str, Enum):
    """安全事件类型，对应领域资料中的“安全事件”。"""

    ROUTE_CLOSURE = "路线封闭"
    LOST_CHILD = "儿童走散"
    BACKUP_GUARDIAN_PICKUP = "备用监护人接回"
    EARLY_FINISH = "提前结束"
    FINISH_NOT_CHECKED_OUT = "终点未核销"


class IncidentStatus(str, Enum):
    OPEN = "待处置"
    RESOLVED = "已解决"


class StaffRole(str, Enum):
    """可见位置等敏感信息的负责岗位。"""

    COMMAND = "指挥席"
    CHECKPOINT = "检查点工作人员"
    MEDICAL = "医疗岗位"


@dataclass
class Member:
    """家庭成员；健康提示需由工作人员在出发前核验。"""

    member_id: str
    name: str
    role: MemberRole
    health_notes: list[str] = field(default_factory=list)
    health_reviewed: bool = False


@dataclass
class EmergencyContact:
    name: str
    phone: str
    relation: str = ""


@dataclass
class GuardianAuthorization:
    """监护授权：某成员可监护某儿童，含备用监护人。"""

    child_id: str
    guardian_id: str
    authorizer: str
    valid: bool = True


@dataclass
class Checkpoint:
    """赛道检查点；distance_km 是沿赛道的里程，计程以此为准。"""

    checkpoint_id: str
    name: str
    sequence: int
    distance_km: float


@dataclass
class Batch:
    """出发批次（组别）。"""

    batch_id: str
    name: str
    wave: int = 1


@dataclass(frozen=True)
class CheckpointRecord:
    """检查点设备产生的记录。

    设备可能离线，联网后批量上传；record_id 全局唯一用于幂等去重，
    occurred_at 是现场真实时间，合并时以它为准，与上传顺序无关。
    """

    record_id: str
    device_id: str
    family_id: str
    checkpoint_id: str
    kind: RecordKind
    occurred_at: datetime
    to_batch_id: str | None = None
    note: str = ""


@dataclass
class HandoverConfirmation:
    """交接确认：工作人员把儿童/家庭交还给监护人或授权备用监护人。"""

    family_id: str
    to_member_id: str
    confirmed_at: datetime
    by_role: StaffRole
    checkpoint_id: str | None = None
    note: str = ""


@dataclass
class Incident:
    incident_id: str
    type: IncidentType
    opened_at: datetime
    family_id: str | None = None
    details: str = ""
    status: IncidentStatus = IncidentStatus.OPEN
    resolved_at: datetime | None = None
    resolution_note: str = ""
    # 路线封闭时使用：受影响的赛道区间（按检查点序号，含头不含尾）
    segment: tuple[int, int] | None = None


@dataclass
class Notification:
    """发给家长的明确联络结果。"""

    family_id: str
    message: str
    created_at: datetime


@dataclass
class Family:
    """参赛家庭及其由检查点记录推导出的行进状态。"""

    family_id: str
    name: str
    members: list[Member] = field(default_factory=list)
    emergency_contacts: list[EmergencyContact] = field(default_factory=list)
    authorizations: list[GuardianAuthorization] = field(default_factory=list)
    batch_id: str | None = None
    status: FamilyStatus = FamilyStatus.PENDING
    # ---- 以下由检查点记录推导，离线合并后重算 ----
    records: list[CheckpointRecord] = field(default_factory=list)
    arrivals: dict[str, datetime] = field(default_factory=dict)
    current_batch_id: str | None = None
    withdrawn: bool = False
    checked_out: bool = False
    medical_open: bool = False
    incident_assistance: bool = False
    handovers: list[HandoverConfirmation] = field(default_factory=list)

    def children(self) -> list[Member]:
        return [m for m in self.members if m.role == MemberRole.CHILD]

    def member(self, member_id: str) -> Member | None:
        return next((m for m in self.members if m.member_id == member_id), None)

    @property
    def awaiting_handover(self) -> bool:
        """已退出或已到终点但尚未完成交接。"""
        return (
            (self.withdrawn or self.checked_out)
            and self.status != FamilyStatus.HANDED_OVER
        )
