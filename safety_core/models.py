"""亲子健走安全联络后台的领域模型。

流程状态用词沿用 fixtures/domain.json 的公开资料约定。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class FamilyState(str, enum.Enum):
    """参赛家庭的流程状态。"""

    待核验 = "待核验"
    已出发 = "已出发"
    行进中 = "行进中"
    需协助 = "需协助"
    已交接 = "已交接"


class EventState(str, enum.Enum):
    """整场比赛的流程状态。"""

    进行中 = "进行中"
    已闭赛 = "已闭赛"


class MemberKind(str, enum.Enum):
    """家庭成员类别。"""

    儿童 = "儿童"
    监护人 = "监护人"
    备用监护人 = "备用监护人"


class CheckpointEventKind(str, enum.Enum):
    """检查点可离线登记的事项。"""

    到达 = "到达"
    退出 = "退出"
    临时转组 = "临时转组"
    医疗观察 = "医疗观察"
    终点核销 = "终点核销"


class IncidentKind(str, enum.Enum):
    """需要分别处置的安全事件。"""

    路线封闭 = "路线封闭"
    儿童走散 = "儿童走散"
    备用监护人接回 = "备用监护人接回"
    提前结束 = "提前结束"
    终点未核销 = "终点未核销"


class IncidentState(str, enum.Enum):
    未解决 = "未解决"
    已解决 = "已解决"


class Role(str, enum.Enum):
    """查询安全资料时使用的岗位角色。"""

    指挥席 = "指挥席"
    检查点岗位 = "检查点岗位"
    医疗岗位 = "医疗岗位"
    家长 = "家长"


#: 负责岗位可以查看赛道位置，其余角色仅限本家庭。
STAFF_ROLES: frozenset[Role] = frozenset({Role.指挥席, Role.检查点岗位, Role.医疗岗位})


@dataclass
class Member:
    """家庭成员，儿童的健康提示随成员记录。"""

    member_id: str
    family_id: str
    name: str
    kind: MemberKind
    health_notes: tuple[str, ...] = ()


@dataclass
class GuardianshipAuthorization:
    """监护授权：某位监护人或备用监护人负责哪些儿童。"""

    auth_id: str
    family_id: str
    guardian_id: str
    child_ids: tuple[str, ...]
    authorized_by: str
    valid: bool = True


@dataclass
class EmergencyContact:
    """紧急联系人，仅供家庭侧联络，不作为工作人员查人途径。"""

    name: str
    relation: str
    phone: str


@dataclass
class Family:
    """参赛家庭。"""

    family_id: str
    group: str
    batch_id: str | None = None
    state: FamilyState = FamilyState.待核验
    health_acknowledged: bool = False
    emergency_contacts: list[EmergencyContact] = field(default_factory=list)
    departed_at: datetime | None = None


@dataclass(frozen=True)
class Checkpoint:
    """检查点，里程为距起点的累计公里数。"""

    checkpoint_id: str
    name: str
    distance_km: float


@dataclass(frozen=True)
class Course:
    """滨江赛道，检查点按路线顺序排列。"""

    checkpoints: tuple[Checkpoint, ...]

    def __post_init__(self) -> None:
        if not self.checkpoints:
            raise ValueError("赛道至少需要一个检查点")

    def has(self, checkpoint_id: str) -> bool:
        return any(c.checkpoint_id == checkpoint_id for c in self.checkpoints)

    def distance_of(self, checkpoint_id: str) -> float:
        for checkpoint in self.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint.distance_km
        raise KeyError(f"未知检查点: {checkpoint_id}")

    def name_of(self, checkpoint_id: str) -> str:
        for checkpoint in self.checkpoints:
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint.name
        raise KeyError(f"未知检查点: {checkpoint_id}")

    @property
    def finish_id(self) -> str:
        return self.checkpoints[-1].checkpoint_id

    @property
    def total_km(self) -> float:
        return self.checkpoints[-1].distance_km


@dataclass
class Batch:
    """出发批次。"""

    batch_id: str
    group: str
    start_at: datetime


@dataclass
class CheckpointEvent:
    """检查点登记。

    离线时由检查点设备生成并保存，event_id 与 occurred_at 由设备确定；
    联网后按 event_id 去重、按 occurred_at 的真实时间顺序合并。
    """

    event_id: str
    family_id: str
    checkpoint_id: str
    kind: CheckpointEventKind
    occurred_at: datetime
    post_id: str
    to_group: str | None = None
    note: str = ""


@dataclass
class Incident:
    """安全事件单。"""

    incident_id: str
    kind: IncidentKind
    opened_at: datetime
    family_id: str | None = None
    group: str | None = None
    detail: str = ""
    state: IncidentState = IncidentState.未解决
    resolution: str = ""
    resolved_at: datetime | None = None


@dataclass
class HandoverConfirmation:
    """交接确认：孩子安全交回监护侧的记录。"""

    family_id: str
    confirmed_by: str
    confirmed_at: datetime
    method: str
    note: str = ""


@dataclass
class Notification:
    """发给家长的明确联络结果。"""

    notification_id: str
    family_id: str
    created_at: datetime
    result: str
    delivered: bool = True


@dataclass(frozen=True)
class FamilyCard:
    """工作人员按标识查到的家庭全貌。"""

    family: Family
    children: tuple[Member, ...]
    guardians: tuple[Member, ...]
    current_group: str
    last_checkpoint_id: str | None
    state: FamilyState


@dataclass(frozen=True)
class FamilySnapshot:
    """指挥席看到的组内一户。"""

    family_id: str
    state: FamilyState
    last_checkpoint_id: str | None
    last_confirmed_at: datetime | None


@dataclass(frozen=True)
class GroupStatus:
    """指挥席看到的单个组别：每户最后确认点与未解决事件。"""

    group: str
    families: tuple[FamilySnapshot, ...]
    unresolved: tuple[Incident, ...]
