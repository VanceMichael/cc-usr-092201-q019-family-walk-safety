"""亲子健走安全联络后台核心服务。

职责：
- 出发前核验家庭成员、监护授权、健康提示、批次与紧急联系人；
- 检查点记录离线登记、联网后按真实时间合并，幂等且不重复计程；
- 安全事件（路线封闭、儿童走散、备用监护人接回、提前结束、终点未核销）处置；
- 交接确认与家长通知；
- 指挥席总览与闭赛闸门：全部人员完成安全交接才允许闭赛。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterable

from .models import (
    Batch,
    Checkpoint,
    CheckpointRecord,
    EmergencyContact,
    EventStatus,
    Family,
    FamilyStatus,
    GuardianAuthorization,
    HandoverConfirmation,
    Incident,
    IncidentStatus,
    IncidentType,
    Member,
    MemberRole,
    Notification,
    RecordKind,
    StaffRole,
)

GUARDIAN_ROLES = {MemberRole.GUARDIAN, MemberRole.BACKUP_GUARDIAN}
ACTIVE_STATUSES = {
    FamilyStatus.DEPARTED,
    FamilyStatus.ON_COURSE,
    FamilyStatus.NEEDS_ASSISTANCE,
}


class RaceService:
    """单场赛事的安全联络后台。"""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.checkpoints: dict[str, Checkpoint] = {}
        self.batches: dict[str, Batch] = {}
        self.families: dict[str, Family] = {}
        self.incidents: dict[str, Incident] = {}
        self.notifications: list[Notification] = []
        self.event_status = EventStatus.RUNNING
        self._record_ids: set[str] = set()
        self._incident_seq = 0

    # ------------------------------------------------------------------
    # 基础资料登记
    # ------------------------------------------------------------------
    def add_checkpoint(self, checkpoint: Checkpoint) -> None:
        self.checkpoints[checkpoint.checkpoint_id] = checkpoint

    def add_batch(self, batch: Batch) -> None:
        self.batches[batch.batch_id] = batch

    def register_family(self, family: Family) -> None:
        if family.family_id in self.families:
            raise ValueError(f"家庭已登记：{family.family_id}")
        family.current_batch_id = family.batch_id
        self.families[family.family_id] = family

    # ------------------------------------------------------------------
    # 出发前核验
    # ------------------------------------------------------------------
    def verify_family(self, family_id: str) -> list[str]:
        """返回核验问题清单；空清单表示可以出发。"""
        fam = self._family(family_id)
        problems: list[str] = []
        if not fam.batch_id or fam.batch_id not in self.batches:
            problems.append("家庭未分配有效出发批次")
        children = fam.children()
        if not children:
            problems.append("家庭缺少儿童成员")
        if not any(m.role == MemberRole.GUARDIAN for m in fam.members):
            problems.append("家庭缺少监护人")
        for child in children:
            if not self._authorized_guardians(fam, child.member_id):
                problems.append(f"儿童 {child.name} 缺少有效监护授权")
            if not child.health_reviewed:
                problems.append(f"儿童 {child.name} 的健康提示尚未核验")
        if not fam.emergency_contacts:
            problems.append("家庭缺少紧急联系人")
        return problems

    def depart_family(self, family_id: str) -> None:
        fam = self._family(family_id)
        if fam.status != FamilyStatus.PENDING:
            raise ValueError(f"家庭当前状态为{fam.status.value}，不能重复出发")
        problems = self.verify_family(family_id)
        if problems:
            raise ValueError("出发前核验未通过：" + "；".join(problems))
        fam.status = FamilyStatus.DEPARTED

    # ------------------------------------------------------------------
    # 检查点记录：离线登记、联网合并
    # ------------------------------------------------------------------
    def apply_record(self, record: CheckpointRecord) -> bool:
        """合并一条检查点记录；重复 record_id 直接忽略，返回是否为新记录。"""
        if record.record_id in self._record_ids:
            return False
        if record.checkpoint_id not in self.checkpoints:
            raise ValueError(f"未知检查点：{record.checkpoint_id}")
        if record.kind == RecordKind.TRANSFER and record.to_batch_id not in self.batches:
            raise ValueError(f"未知批次：{record.to_batch_id}")
        fam = self._family(record.family_id)
        self._record_ids.add(record.record_id)
        fam.records.append(record)
        self._refresh(fam)
        return True

    def sync_records(self, records: Iterable[CheckpointRecord]) -> int:
        """设备联网后批量上传；按真实时间排序合并，与上传顺序无关。"""
        ordered = sorted(records, key=lambda r: (r.occurred_at, r.record_id))
        return sum(1 for r in ordered if self.apply_record(r))

    def _refresh(self, fam: Family) -> None:
        """由全部已合并记录重算家庭行进状态，保证离线乱序合并结果一致。"""
        arrivals: dict[str, datetime] = {}
        transfers: list[tuple[datetime, str]] = []
        withdrawals: list[datetime] = []
        medicals: list[datetime] = []
        checked_out = False
        for r in fam.records:
            if r.kind == RecordKind.ARRIVAL:
                prev = arrivals.get(r.checkpoint_id)
                if prev is None or r.occurred_at < prev:
                    arrivals[r.checkpoint_id] = r.occurred_at
            elif r.kind == RecordKind.TRANSFER and r.to_batch_id:
                transfers.append((r.occurred_at, r.to_batch_id))
            elif r.kind == RecordKind.WITHDRAWAL:
                withdrawals.append(r.occurred_at)
            elif r.kind == RecordKind.MEDICAL_OBSERVATION:
                medicals.append(r.occurred_at)
            elif r.kind == RecordKind.CHECKOUT:
                checked_out = True
        fam.arrivals = arrivals
        fam.current_batch_id = (
            max(transfers)[1] if transfers else fam.batch_id
        )
        last_arrival = max(arrivals.values()) if arrivals else None
        # 退出 / 医疗观察只在其为最新现场事实时生效
        fam.withdrawn = bool(withdrawals) and (
            last_arrival is None or max(withdrawals) > last_arrival
        )
        fam.medical_open = bool(medicals) and (
            last_arrival is None or max(medicals) > last_arrival
        )
        fam.checked_out = checked_out
        if fam.status in (FamilyStatus.PENDING, FamilyStatus.HANDED_OVER):
            return
        if fam.medical_open or fam.incident_assistance:
            fam.status = FamilyStatus.NEEDS_ASSISTANCE
        elif arrivals:
            fam.status = FamilyStatus.ON_COURSE
        else:
            fam.status = FamilyStatus.DEPARTED

    # ------------------------------------------------------------------
    # 位置与计程（计程取检查点里程，重复记录不会重复计程）
    # ------------------------------------------------------------------
    def last_confirmed_checkpoint(self, family_id: str) -> Checkpoint | None:
        fam = self._family(family_id)
        if not fam.arrivals:
            return None
        return max(
            (self.checkpoints[cid] for cid in fam.arrivals),
            key=lambda c: c.sequence,
        )

    def family_distance_km(self, family_id: str) -> float:
        cp = self.last_confirmed_checkpoint(family_id)
        return cp.distance_km if cp else 0.0

    # ------------------------------------------------------------------
    # 交接确认
    # ------------------------------------------------------------------
    def confirm_handover(
        self,
        family_id: str,
        to_member_id: str,
        by_role: StaffRole,
        checkpoint_id: str | None = None,
        note: str = "",
    ) -> HandoverConfirmation:
        fam = self._family(family_id)
        if fam.status == FamilyStatus.PENDING:
            raise ValueError("家庭尚未出发，无需交接")
        if fam.status == FamilyStatus.HANDED_OVER:
            raise ValueError("家庭已完成交接")
        member = fam.member(to_member_id)
        if member is None or member.role not in GUARDIAN_ROLES:
            raise ValueError("交接对象必须是本家庭的监护人或备用监护人")
        for child in fam.children():
            if not any(
                a.guardian_id == to_member_id and a.valid
                for a in fam.authorizations
                if a.child_id == child.member_id
            ):
                raise ValueError(
                    f"交接对象对儿童 {child.name} 没有有效监护授权"
                )
        handover = HandoverConfirmation(
            family_id=family_id,
            to_member_id=to_member_id,
            confirmed_at=self._clock(),
            by_role=by_role,
            checkpoint_id=checkpoint_id,
            note=note,
        )
        fam.handovers.append(handover)
        fam.incident_assistance = False
        fam.status = FamilyStatus.HANDED_OVER
        self._notify(fam, f"已完成安全交接：{fam.name} 由 {member.name} 接回。")
        return handover

    # ------------------------------------------------------------------
    # 安全事件
    # ------------------------------------------------------------------
    def open_incident(
        self,
        type: IncidentType,
        family_id: str | None = None,
        details: str = "",
        segment: tuple[int, int] | None = None,
    ) -> Incident:
        if type == IncidentType.ROUTE_CLOSURE and segment is None:
            raise ValueError("路线封闭必须给出受影响区间")
        self._incident_seq += 1
        incident = Incident(
            incident_id=f"INC-{self._incident_seq:04d}",
            type=type,
            opened_at=self._clock(),
            family_id=family_id,
            details=details,
            segment=segment,
        )
        self.incidents[incident.incident_id] = incident
        if family_id is not None:
            fam = self._family(family_id)
            if type in (IncidentType.LOST_CHILD, IncidentType.BACKUP_GUARDIAN_PICKUP):
                fam.incident_assistance = True
                self._refresh(fam)
            self._notify(fam, f"已受理安全事件「{type.value}」，工作人员将主动联系。")
        return incident

    def resolve_incident(self, incident_id: str, note: str = "") -> Incident:
        incident = self._incident(incident_id)
        if incident.status == IncidentStatus.RESOLVED:
            raise ValueError("事件已解决")
        problem = self._resolution_problem(incident)
        if problem:
            self._fail(problem)
        incident.status = IncidentStatus.RESOLVED
        incident.resolved_at = self._clock()
        incident.resolution_note = note
        if incident.family_id:
            fam = self._family(incident.family_id)
            self._notify(fam, f"安全事件「{incident.type.value}」已解决：{note or '处置完成'}。")
        return incident

    def _resolution_problem(self, incident: Incident) -> str | None:
        fam = self.families.get(incident.family_id) if incident.family_id else None
        t = incident.type
        if t == IncidentType.LOST_CHILD:
            if not fam or fam.status != FamilyStatus.HANDED_OVER:
                return "儿童走散须先完成与监护人或授权备用监护人的交接"
            if not any(h.confirmed_at >= incident.opened_at for h in fam.handovers):
                return "交接确认必须发生在事件受理之后"
        elif t == IncidentType.BACKUP_GUARDIAN_PICKUP:
            if not fam or not any(
                h.confirmed_at >= incident.opened_at
                and (m := fam.member(h.to_member_id))
                and m.role == MemberRole.BACKUP_GUARDIAN
                for h in fam.handovers
            ):
                return "须由已授权的备用监护人完成接回交接"
        elif t == IncidentType.EARLY_FINISH:
            if not fam or not fam.withdrawn:
                return "提前结束须先在检查点登记退出"
            if fam.status != FamilyStatus.HANDED_OVER:
                return "提前结束须完成安全交接"
        elif t == IncidentType.FINISH_NOT_CHECKED_OUT:
            if not fam or not (fam.checked_out or fam.status == FamilyStatus.HANDED_OVER):
                return "终点未核销须补做终点核销或完成交接"
        elif t == IncidentType.ROUTE_CLOSURE:
            lo, hi = incident.segment or (0, 0)
            for other in self.families.values():
                if other.status not in ACTIVE_STATUSES:
                    continue
                cp = self.last_confirmed_checkpoint(other.family_id)
                if cp and lo <= cp.sequence < hi:
                    return f"封闭区间内仍有未安置家庭：{other.name}"
        return None

    def sweep_finish_not_checked_out(self) -> list[Incident]:
        """巡检：到达终点检查点却未核销也未交接的家庭，自动开立事件。"""
        finish = self._finish_checkpoint()
        opened: list[Incident] = []
        for fam in self.families.values():
            if finish.checkpoint_id not in fam.arrivals:
                continue
            if fam.checked_out or fam.status == FamilyStatus.HANDED_OVER:
                continue
            if any(
                i.family_id == fam.family_id
                and i.type == IncidentType.FINISH_NOT_CHECKED_OUT
                and i.status == IncidentStatus.OPEN
                for i in self.incidents.values()
            ):
                continue
            opened.append(
                self.open_incident(
                    IncidentType.FINISH_NOT_CHECKED_OUT,
                    family_id=fam.family_id,
                    details="已到达终点检查点但未完成终点核销",
                )
            )
        return opened

    # ------------------------------------------------------------------
    # 指挥席
    # ------------------------------------------------------------------
    def group_overview(self, batch_id: str) -> dict:
        """某组每家庭的最后确认点、待交接与未解决事件。"""
        if batch_id not in self.batches:
            raise ValueError(f"未知批次：{batch_id}")
        rows = []
        trailing: Checkpoint | None = None
        for fam in self.families.values():
            if fam.current_batch_id != batch_id:
                continue
            cp = self.last_confirmed_checkpoint(fam.family_id)
            rows.append(
                {
                    "family_id": fam.family_id,
                    "family": fam.name,
                    "status": fam.status.value,
                    "last_checkpoint": cp.name if cp else None,
                    "distance_km": cp.distance_km if cp else 0.0,
                    "awaiting_handover": fam.awaiting_handover,
                }
            )
            if fam.status in ACTIVE_STATUSES and cp is not None:
                if trailing is None or cp.sequence < trailing.sequence:
                    trailing = cp
        return {
            "batch_id": batch_id,
            "batch": self.batches[batch_id].name,
            "families": rows,
            "trailing_checkpoint": trailing.name if trailing else None,
            "unresolved_incidents": [
                i.incident_id
                for i in self.incidents.values()
                if i.status == IncidentStatus.OPEN
                and any(r["family_id"] == i.family_id for r in rows)
            ],
        }

    def unresolved_incidents(self) -> list[Incident]:
        return [i for i in self.incidents.values() if i.status == IncidentStatus.OPEN]

    def family_notifications(self, family_id: str) -> list[Notification]:
        return [n for n in self.notifications if n.family_id == family_id]

    # ------------------------------------------------------------------
    # 闭赛闸门
    # ------------------------------------------------------------------
    def close_event(self) -> None:
        problems: list[str] = []
        for fam in self.families.values():
            if fam.status != FamilyStatus.HANDED_OVER:
                problems.append(f"家庭 {fam.name} 尚未完成安全交接（{fam.status.value}）")
        for incident in self.unresolved_incidents():
            problems.append(f"事件 {incident.incident_id}（{incident.type.value}）仍未解决")
        if problems:
            raise ValueError("不允许闭赛：" + "；".join(problems))
        self.event_status = EventStatus.CLOSED

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _family(self, family_id: str) -> Family:
        try:
            return self.families[family_id]
        except KeyError:
            raise ValueError(f"未知家庭：{family_id}") from None

    def _incident(self, incident_id: str) -> Incident:
        try:
            return self.incidents[incident_id]
        except KeyError:
            raise ValueError(f"未知事件：{incident_id}") from None

    def _finish_checkpoint(self) -> Checkpoint:
        if not self.checkpoints:
            raise ValueError("尚未登记检查点")
        return max(self.checkpoints.values(), key=lambda c: c.sequence)

    def _authorized_guardians(self, fam: Family, child_id: str) -> list[str]:
        member_ids = {m.member_id for m in fam.members if m.role in GUARDIAN_ROLES}
        return [
            a.guardian_id
            for a in fam.authorizations
            if a.child_id == child_id and a.valid and a.guardian_id in member_ids
        ]

    def _notify(self, fam: Family, message: str) -> None:
        self.notifications.append(
            Notification(family_id=fam.family_id, message=message, created_at=self._clock())
        )

    @staticmethod
    def _fail(message: str) -> None:
        raise ValueError(message)
