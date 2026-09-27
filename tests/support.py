"""测试共用的搭建工具。"""

from datetime import datetime, timedelta, timezone

from safety_core import (
    Batch,
    Checkpoint,
    CheckpointEvent,
    CheckpointEventKind,
    Course,
    EmergencyContact,
    Family,
    GuardianshipAuthorization,
    Member,
    MemberKind,
    RaceControl,
)

BASE = datetime(2026, 9, 26, 8, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    """赛事当天 BASE 之后第几分钟。"""
    return BASE + timedelta(minutes=minutes)


def make_course() -> Course:
    """13.5 公里滨江赛道，途经水间留趣、望江楼。"""
    return Course(
        checkpoints=(
            Checkpoint("CP0", "起点", 0.0),
            Checkpoint("CP1", "水间留趣", 4.5),
            Checkpoint("CP2", "望江楼", 9.0),
            Checkpoint("CP3", "终点", 13.5),
        )
    )


def make_control() -> RaceControl:
    control = RaceControl(make_course())
    control.register_batch(Batch("B1", "中将组", BASE))
    control.register_batch(Batch("B2", "慢行组", BASE))
    return control


def add_family(
    control: RaceControl,
    family_id: str = "FAM-092201-019",
    group: str = "中将组",
    *,
    batch_id: str | None = "B1",
    health_acknowledged: bool = True,
    with_contact: bool = True,
    with_authorization: bool = True,
    with_backup_guardian: bool = False,
) -> Family:
    """登记一户资料可配的家庭，默认满足全部出发条件。"""
    family = Family(
        family_id, group, batch_id=batch_id, health_acknowledged=health_acknowledged
    )
    if with_contact:
        family.emergency_contacts.append(EmergencyContact("王女士", "祖母", "138****0000"))
    members = [
        Member(f"{family_id}-C1", family_id, "小明", MemberKind.儿童),
        Member(f"{family_id}-G1", family_id, "张先生", MemberKind.监护人),
    ]
    auths = []
    if with_authorization:
        auths.append(
            GuardianshipAuthorization(
                f"{family_id}-A1", family_id, f"{family_id}-G1", (f"{family_id}-C1",), "报名处"
            )
        )
    if with_backup_guardian:
        members.append(Member(f"{family_id}-B1", family_id, "李女士", MemberKind.备用监护人))
        auths.append(
            GuardianshipAuthorization(
                f"{family_id}-A2", family_id, f"{family_id}-B1", (f"{family_id}-C1",), "报名处"
            )
        )
    control.register_family(family, members, auths)
    return family


def depart(control: RaceControl, family_id: str) -> None:
    control.depart(family_id, now=at(0))


def event(
    event_id: str,
    family_id: str,
    checkpoint_id: str,
    minutes: int,
    kind: CheckpointEventKind = CheckpointEventKind.到达,
    to_group: str | None = None,
) -> CheckpointEvent:
    return CheckpointEvent(
        event_id=event_id,
        family_id=family_id,
        checkpoint_id=checkpoint_id,
        kind=kind,
        occurred_at=at(minutes),
        post_id="POST-1",
        to_group=to_group,
    )
