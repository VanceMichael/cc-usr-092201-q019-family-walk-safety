"""安全联络后台门面：把核验、登记、事件、交接与闭赛串成一条线。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from . import closure, disclosure
from .closure import CloseReadiness
from .incidents import IncidentDesk
from .models import (
    Batch,
    CheckpointEvent,
    CheckpointEventKind,
    Course,
    EventState,
    Family,
    FamilyCard,
    FamilySnapshot,
    FamilyState,
    GroupStatus,
    GuardianshipAuthorization,
    HandoverConfirmation,
    Incident,
    IncidentKind,
    Member,
    MemberKind,
    Role,
)
from .notifications import NotificationLog
from .tracking import CheckpointLog, FamilyProgress
from .verification import VerificationResult, verify_family

#: 销单时必须同时完成交接确认的事件类型
_HANDOVER_INCIDENTS = (
    IncidentKind.备用监护人接回,
    IncidentKind.提前结束,
    IncidentKind.终点未核销,
)


class RaceControl:
    """一场亲子健走的安全联络后台。"""

    def __init__(self, course: Course) -> None:
        self.course = course
        self.event_state = EventState.进行中
        self.families: dict[str, Family] = {}
        self.members: dict[str, Member] = {}
        self.authorizations: dict[str, GuardianshipAuthorization] = {}
        self.batches: dict[str, Batch] = {}
        self.handovers: dict[str, HandoverConfirmation] = {}
        self.log = CheckpointLog(course)
        self.incidents = IncidentDesk()
        self.notifications = NotificationLog()

    # ---- 报名与出发前核验 ----

    def register_batch(self, batch: Batch) -> None:
        self.batches[batch.batch_id] = batch

    def register_family(
        self,
        family: Family,
        members: Iterable[Member] = (),
        authorizations: Iterable[GuardianshipAuthorization] = (),
    ) -> None:
        if family.family_id in self.families:
            raise ValueError(f"家庭已登记: {family.family_id}")
        self.families[family.family_id] = family
        for member in members:
            if member.family_id != family.family_id:
                raise ValueError("成员与家庭标识不一致")
            self.members[member.member_id] = member
        for auth in authorizations:
            if auth.family_id != family.family_id:
                raise ValueError("监护授权与家庭标识不一致")
            self.authorizations[auth.auth_id] = auth

    def verify_family(self, family_id: str) -> VerificationResult:
        """出发前核验：家庭成员、监护授权、健康提示、批次、紧急联系人。"""
        family = self.families[family_id]
        return verify_family(
            family,
            self._members_of(family_id),
            self._auths_of(family_id),
            known_batch_ids=set(self.batches),
        )

    def depart(self, family_id: str, *, now: datetime) -> None:
        """核验通过才允许出发，状态由待核验转为已出发。"""
        family = self.families[family_id]
        if family.state != FamilyState.待核验:
            raise ValueError(f"家庭 {family_id} 当前状态不允许出发")
        result = self.verify_family(family_id)
        if not result.ok:
            raise ValueError("出发前核验未通过: " + "；".join(result.problems))
        family.departed_at = now
        family.state = FamilyState.已出发

    # ---- 检查点登记与离线合并 ----

    def record_event(self, event: CheckpointEvent) -> None:
        """登记一条检查点记录（在线或离线设备本地），重复上报自动忽略。"""
        self._require_family(event.family_id)
        if self.log.merge([event]):
            self._after_event(event)

    def sync_events(self, events: Iterable[CheckpointEvent]) -> list[CheckpointEvent]:
        """联网后合并离线记录，按真实时间生效且不重复计程。"""
        events = list(events)
        for event in events:
            self._require_family(event.family_id)
        added = self.log.merge(events)
        for event in added:
            self._after_event(event)
        return added

    def progress(self, family_id: str) -> FamilyProgress:
        family = self.families[family_id]
        return self.log.progress(family_id, base_group=family.group)

    # ---- 安全事件处置 ----

    def report_lost_child(self, family_id: str, *, now: datetime, detail: str = "") -> Incident:
        """儿童走散：立即建单，家庭转为需协助。"""
        self._require_family(family_id)
        last = self.log.progress(family_id).last_checkpoint_id
        location = f"，最后确认点 {self.course.name_of(last)}" if last else ""
        incident = self._raise_once(
            IncidentKind.儿童走散,
            family_id=family_id,
            now=now,
            detail=detail or f"儿童与监护人走散{location}",
        )
        self._refresh_state(family_id)
        return incident

    def request_backup_guardian_pickup(
        self, family_id: str, guardian_id: str, *, now: datetime
    ) -> Incident:
        """备用监护人接回：必须是本家庭登记且持有效授权的备用监护人。"""
        self._require_family(family_id)
        member = self.members.get(guardian_id)
        if member is None or member.family_id != family_id or member.kind != MemberKind.备用监护人:
            raise ValueError("接回人不是本家庭登记的备用监护人")
        authorized = any(
            auth.valid and auth.guardian_id == guardian_id
            for auth in self._auths_of(family_id)
        )
        if not authorized:
            raise ValueError("备用监护人缺少有效监护授权")
        incident = self._raise_once(
            IncidentKind.备用监护人接回,
            family_id=family_id,
            now=now,
            detail=f"由备用监护人 {member.name} 接回",
        )
        self._refresh_state(family_id)
        return incident

    def close_route(self, *, now: datetime, group: str | None = None, detail: str = "路线封闭") -> Incident:
        """路线封闭：建单并通知受影响家庭前往最近检查点等候。"""
        incident = self.incidents.raise_incident(
            IncidentKind.路线封闭, now=now, group=group, detail=detail
        )
        for family in self._affected_families(group):
            self.notifications.notify(
                family.family_id,
                result=f"路线封闭：{detail}，请前往最近检查点等候指引",
                now=now,
            )
        return incident

    def detect_missing_finish(self, *, now: datetime) -> list[Incident]:
        """终点未核销排查：已出发但未核销也未交接的家庭逐户建单。"""
        raised = []
        for family in self.families.values():
            if family.departed_at is None or family.family_id in self.handovers:
                continue
            if self.incidents.has_unresolved(IncidentKind.终点未核销, family.family_id):
                continue
            progress = self.log.progress(family.family_id)
            if progress.finished or progress.exited:
                continue
            raised.append(
                self._raise_once(
                    IncidentKind.终点未核销,
                    family_id=family.family_id,
                    now=now,
                    detail="终点未核销，需确认人员去向",
                )
            )
        return raised

    def resolve_incident(
        self,
        incident_id: str,
        *,
        resolution: str,
        now: datetime,
        handover_by: str | None = None,
    ) -> Incident:
        """销单：记录处置结果；需要交接的事件先完成交接；家长收到明确结果。"""
        incident = self.incidents.get(incident_id)
        needs_handover = (
            incident.kind in _HANDOVER_INCIDENTS
            and incident.family_id is not None
            and incident.family_id not in self.handovers
        )
        if needs_handover and not handover_by:
            raise ValueError(f"{incident.kind.value} 销单前必须完成交接确认")
        self.incidents.resolve(incident_id, resolution=resolution, now=now)
        if needs_handover:
            self.confirm_handover(
                incident.family_id,
                by=handover_by,
                method=incident.kind.value,
                now=now,
                note=resolution,
            )
        if incident.family_id is not None:
            self.notifications.notify(
                incident.family_id,
                result=f"{incident.kind.value}处理结果：{resolution}",
                now=now,
            )
            self._refresh_state(incident.family_id)
        elif incident.kind == IncidentKind.路线封闭:
            for family in self._affected_families(incident.group):
                self.notifications.notify(
                    family.family_id,
                    result=f"路线封闭处理结果：{resolution}",
                    now=now,
                )
        return incident

    # ---- 交接与闭赛 ----

    def confirm_handover(
        self, family_id: str, *, by: str, method: str, now: datetime, note: str = ""
    ) -> HandoverConfirmation:
        """记录交接确认；家庭转为已交接。"""
        self._require_family(family_id)
        if family_id in self.handovers:
            raise ValueError(f"家庭 {family_id} 已完成交接，不能重复确认")
        handover = HandoverConfirmation(
            family_id=family_id,
            confirmed_by=by,
            confirmed_at=now,
            method=method,
            note=note,
        )
        self.handovers[family_id] = handover
        self._refresh_state(family_id)
        return handover

    def close_readiness(self) -> CloseReadiness:
        return closure.close_readiness(
            families=list(self.families.values()),
            handed_over_ids=set(self.handovers),
            desk=self.incidents,
        )

    def close_event(self, *, now: datetime) -> None:
        """全部人员完成安全交接才允许闭赛，而不是看到完赛数字就结束。"""
        readiness = self.close_readiness()
        if not readiness.can_close:
            problems = []
            if readiness.pending_families:
                problems.append("未完成交接: " + ", ".join(readiness.pending_families))
            if readiness.unresolved_incidents:
                problems.append("未解决事件: " + ", ".join(readiness.unresolved_incidents))
            raise RuntimeError("尚不满足闭赛条件——" + "；".join(problems))
        self.event_state = EventState.已闭赛

    # ---- 查询：身份对应、位置披露、指挥席 ----

    def lookup(self, id_or_member: str) -> FamilyCard:
        """按家庭或成员标识直接定位，不经过报名手机号逐级转问。"""
        family_id = id_or_member
        if family_id not in self.families:
            member = self.members.get(id_or_member)
            if member is None:
                raise KeyError(f"查不到标识: {id_or_member}")
            family_id = member.family_id
        family = self.families[family_id]
        members = self._members_of(family_id)
        progress = self.log.progress(family_id, base_group=family.group)
        return FamilyCard(
            family=family,
            children=tuple(m for m in members if m.kind == MemberKind.儿童),
            guardians=tuple(m for m in members if m.kind != MemberKind.儿童),
            current_group=progress.current_group or family.group,
            last_checkpoint_id=progress.last_checkpoint_id,
            state=family.state,
        )

    def location_for(
        self, family_id: str, *, role: Role, viewer_family_id: str | None = None
    ) -> str | None:
        """位置只向负责岗位及本家庭披露，其余返回 None。"""
        if not disclosure.can_view_location(
            role, viewer_family_id=viewer_family_id, target_family_id=family_id
        ):
            return None
        return self.log.progress(family_id).last_checkpoint_id

    def group_status(self, group: str) -> GroupStatus:
        """指挥席视角：组内每户的最后确认点与状态，以及仍未解决的事件。"""
        snapshots = []
        for family in self.families.values():
            progress = self.log.progress(family.family_id, base_group=family.group)
            if (progress.current_group or family.group) != group:
                continue
            snapshots.append(
                FamilySnapshot(
                    family_id=family.family_id,
                    state=family.state,
                    last_checkpoint_id=progress.last_checkpoint_id,
                    last_confirmed_at=progress.last_confirmed_at,
                )
            )
        unresolved = [
            incident
            for incident in self.incidents.unresolved()
            if incident.group == group
            or (
                incident.family_id is not None
                and self.lookup(incident.family_id).current_group == group
            )
        ]
        return GroupStatus(
            group=group,
            families=tuple(sorted(snapshots, key=lambda s: s.family_id)),
            unresolved=tuple(unresolved),
        )

    # ---- 内部 ----

    def _after_event(self, event: CheckpointEvent) -> None:
        if event.kind == CheckpointEventKind.退出:
            self._raise_once(
                IncidentKind.提前结束,
                family_id=event.family_id,
                now=event.occurred_at,
                detail=f"在 {self.course.name_of(event.checkpoint_id)} 登记退出",
            )
        elif event.kind == CheckpointEventKind.医疗观察:
            self.notifications.notify(
                event.family_id,
                result=f"已在{self.course.name_of(event.checkpoint_id)}接受医疗观察，工作人员持续关注",
                now=event.occurred_at,
            )
        self._refresh_state(event.family_id)

    def _raise_once(
        self,
        kind: IncidentKind,
        *,
        now: datetime,
        family_id: str | None = None,
        group: str | None = None,
        detail: str = "",
    ) -> Incident:
        """建单并给家长留受理回执；同类未解决事件不重复建单。"""
        if family_id is not None:
            existing = self.incidents.find_unresolved(kind, family_id)
            if existing is not None:
                return existing
        incident = self.incidents.raise_incident(
            kind, now=now, family_id=family_id, group=group, detail=detail
        )
        if family_id is not None:
            self.notifications.notify(
                family_id,
                result=f"{kind.value}已受理：{detail or '工作人员正在处理'}",
                now=now,
            )
        return incident

    def _refresh_state(self, family_id: str) -> None:
        family = self.families[family_id]
        if family.family_id in self.handovers:
            family.state = FamilyState.已交接
            return
        if family.departed_at is None:
            family.state = FamilyState.待核验
            return
        progress = self.log.progress(family_id)
        needs_help = progress.under_medical_observation or self.incidents.has_unresolved(
            IncidentKind.儿童走散, family_id
        )
        if needs_help:
            family.state = FamilyState.需协助
        elif progress.last_checkpoint_id is not None:
            family.state = FamilyState.行进中
        else:
            family.state = FamilyState.已出发

    def _affected_families(self, group: str | None) -> list[Family]:
        """赛道上受路线封闭影响的家庭（已出发且未交接）。"""
        affected = []
        for family in self.families.values():
            if family.departed_at is None or family.family_id in self.handovers:
                continue
            progress = self.log.progress(family.family_id, base_group=family.group)
            if group is None or (progress.current_group or family.group) == group:
                affected.append(family)
        return affected

    def _require_family(self, family_id: str) -> None:
        if family_id not in self.families:
            raise KeyError(f"未知家庭: {family_id}")

    def _members_of(self, family_id: str) -> list[Member]:
        return [m for m in self.members.values() if m.family_id == family_id]

    def _auths_of(self, family_id: str) -> list[GuardianshipAuthorization]:
        return [a for a in self.authorizations.values() if a.family_id == family_id]
