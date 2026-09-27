import unittest
from datetime import timedelta

from safety_ops import FamilyStatus, IncidentStatus, IncidentType, RecordKind, StaffRole
from support import BASE, build_service, make_family, record


class IncidentTest(unittest.TestCase):
    def setUp(self):
        self.svc, self.clock = build_service()
        self.fam = make_family(with_backup=True)
        self.svc.register_family(self.fam)
        self.svc.depart_family(self.fam.family_id)

    def _arrive(self, fam, cp, hours):
        self.svc.apply_record(
            record(f"ARR-{fam.family_id}-{cp}", fam.family_id, cp, RecordKind.ARRIVAL,
                   BASE + timedelta(hours=hours))
        )

    def test_lost_child_requires_handover_before_resolution(self):
        inc = self.svc.open_incident(
            IncidentType.LOST_CHILD, family_id=self.fam.family_id, details="孩子在 CP1 走散"
        )
        self.assertEqual(self.fam.status, FamilyStatus.NEEDS_ASSISTANCE)
        # 家长收到已受理的联络结果
        self.assertTrue(any("儿童走散" in n.message
                            for n in self.svc.family_notifications(self.fam.family_id)))
        with self.assertRaises(ValueError):
            self.svc.resolve_incident(inc.incident_id)
        self.svc.confirm_handover(
            self.fam.family_id, f"{self.fam.family_id}-G1", StaffRole.CHECKPOINT
        )
        self.svc.resolve_incident(inc.incident_id, note="孩子已回到监护人身边")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)
        messages = [n.message for n in self.svc.family_notifications(self.fam.family_id)]
        self.assertTrue(any("已解决" in m for m in messages))

    def test_backup_guardian_pickup_requires_authorized_backup(self):
        inc = self.svc.open_incident(
            IncidentType.BACKUP_GUARDIAN_PICKUP, family_id=self.fam.family_id
        )
        with self.assertRaises(ValueError):
            self.svc.confirm_handover(
                self.fam.family_id, "陌生人", StaffRole.CHECKPOINT
            )
        self.svc.confirm_handover(
            self.fam.family_id, f"{self.fam.family_id}-B1", StaffRole.CHECKPOINT
        )
        self.svc.resolve_incident(inc.incident_id, note="备用监护人接回")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)

    def test_handover_rejects_member_without_authorization(self):
        other = make_family(family_id="FAM-9")
        self.svc.register_family(other)
        self.svc.depart_family(other.family_id)
        # 其他家庭的监护人对本家庭儿童没有授权
        with self.assertRaises(ValueError):
            self.svc.confirm_handover(
                self.fam.family_id, f"{other.family_id}-G1", StaffRole.CHECKPOINT
            )

    def test_early_finish_needs_withdrawal_and_handover(self):
        inc = self.svc.open_incident(
            IncidentType.EARLY_FINISH, family_id=self.fam.family_id
        )
        with self.assertRaises(ValueError):
            self.svc.resolve_incident(inc.incident_id)
        self.svc.apply_record(
            record("W1", self.fam.family_id, "CP2", RecordKind.WITHDRAWAL,
                   BASE + timedelta(hours=2))
        )
        with self.assertRaises(ValueError):
            self.svc.resolve_incident(inc.incident_id)
        self.svc.confirm_handover(
            self.fam.family_id, f"{self.fam.family_id}-G1", StaffRole.CHECKPOINT,
            checkpoint_id="CP2",
        )
        self.svc.resolve_incident(inc.incident_id, note="提前结束，已交接")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)

    def test_finish_not_checked_out_sweep_and_resolution(self):
        self._arrive(self.fam, "CP4", 3)
        opened = self.svc.sweep_finish_not_checked_out()
        self.assertEqual(len(opened), 1)
        # 重复巡检不会重复开立
        self.assertEqual(self.svc.sweep_finish_not_checked_out(), [])
        inc = opened[0]
        with self.assertRaises(ValueError):
            self.svc.resolve_incident(inc.incident_id)
        self.svc.apply_record(
            record("CO1", self.fam.family_id, "CP4", RecordKind.CHECKOUT,
                   BASE + timedelta(hours=3, minutes=5))
        )
        self.svc.resolve_incident(inc.incident_id, note="补做终点核销")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)

    def test_route_closure_blocked_until_segment_clear(self):
        other = make_family(family_id="FAM-2")
        self.svc.register_family(other)
        self.svc.depart_family(other.family_id)
        self._arrive(self.fam, "CP1", 1)   # 在封闭区间内
        self._arrive(other, "CP3", 1)      # 在区间外
        inc = self.svc.open_incident(
            IncidentType.ROUTE_CLOSURE, segment=(1, 3), details="滨江步道段临时封闭"
        )
        with self.assertRaises(ValueError):
            self.svc.resolve_incident(inc.incident_id)
        # 区间内家庭由工作人员安置交接后，才允许结案
        self.svc.confirm_handover(
            self.fam.family_id, f"{self.fam.family_id}-G1", StaffRole.CHECKPOINT
        )
        self.svc.resolve_incident(inc.incident_id, note="区间清空，改道完成")
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)


if __name__ == "__main__":
    unittest.main()
