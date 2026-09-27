"""测试共用的赛事数据构造。"""

from datetime import datetime, timedelta, timezone

from safety_ops import (
    Batch,
    Checkpoint,
    EmergencyContact,
    Family,
    GuardianAuthorization,
    Member,
    MemberRole,
    RaceService,
)

BASE = datetime(2026, 9, 27, 8, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = BASE

    def __call__(self):
        return self.now

    def advance(self, minutes):
        self.now += timedelta(minutes=minutes)


CHECKPOINTS = [
    Checkpoint("CP0", "起点", 0, 0.0),
    Checkpoint("CP1", "滨江步道", 1, 3.0),
    Checkpoint("CP2", "水间留趣", 2, 6.5),
    Checkpoint("CP3", "城市阳台", 3, 10.0),
    Checkpoint("CP4", "终点", 4, 13.5),
]


def build_service():
    clock = Clock()
    svc = RaceService(clock=clock)
    for cp in CHECKPOINTS:
        svc.add_checkpoint(cp)
    svc.add_batch(Batch("B1", "先锋组", wave=1))
    svc.add_batch(Batch("B2", "中将组", wave=2))
    return svc, clock


def make_family(family_id="FAM-1", batch_id="B1", with_backup=False):
    members = [
        Member(f"{family_id}-C1", "孩子", MemberRole.CHILD, health_reviewed=True),
        Member(f"{family_id}-G1", "家长", MemberRole.GUARDIAN, health_reviewed=True),
    ]
    auths = [
        GuardianAuthorization(f"{family_id}-C1", f"{family_id}-G1", "报名系统"),
    ]
    if with_backup:
        members.append(
            Member(f"{family_id}-B1", "祖辈", MemberRole.BACKUP_GUARDIAN, health_reviewed=True)
        )
        auths.append(
            GuardianAuthorization(f"{family_id}-C1", f"{family_id}-B1", "家长授权")
        )
    return Family(
        family_id=family_id,
        name=f"家庭{family_id}",
        members=members,
        emergency_contacts=[EmergencyContact("联系人", "0000-0000", "亲属")],
        authorizations=auths,
        batch_id=batch_id,
    )


def record(record_id, family_id, checkpoint_id, kind, at, **kwargs):
    from safety_ops import CheckpointRecord

    return CheckpointRecord(
        record_id=record_id,
        device_id="DEV-1",
        family_id=family_id,
        checkpoint_id=checkpoint_id,
        kind=kind,
        occurred_at=at,
        **kwargs,
    )
