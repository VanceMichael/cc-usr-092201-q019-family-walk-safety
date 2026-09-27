import unittest
from datetime import timedelta

from safety_ops import FamilyStatus, RecordKind
from support import BASE, build_service, make_family, record


class OfflineMergeTest(unittest.TestCase):
    def setUp(self):
        self.svc, _ = build_service()
        self.fam = make_family()
        self.svc.register_family(self.fam)
        self.svc.depart_family(self.fam.family_id)

    def test_out_of_order_sync_merges_by_real_time(self):
        # 离线设备联网后乱序上传：先传 CP2 的记录，再传更早的 CP1
        t1, t2 = BASE + timedelta(hours=1), BASE + timedelta(hours=2)
        self.svc.sync_records([
            record("R2", self.fam.family_id, "CP2", RecordKind.ARRIVAL, t2),
            record("R1", self.fam.family_id, "CP1", RecordKind.ARRIVAL, t1),
        ])
        cp = self.svc.last_confirmed_checkpoint(self.fam.family_id)
        self.assertEqual(cp.checkpoint_id, "CP2")
        self.assertEqual(self.svc.family_distance_km(self.fam.family_id), 6.5)
        self.assertEqual(self.fam.status, FamilyStatus.ON_COURSE)

    def test_duplicate_records_are_idempotent_and_not_double_counted(self):
        t1 = BASE + timedelta(hours=1)
        r = record("R1", self.fam.family_id, "CP1", RecordKind.ARRIVAL, t1)
        self.assertTrue(self.svc.apply_record(r))
        self.assertFalse(self.svc.apply_record(r))
        self.assertFalse(self.svc.apply_record(r))
        self.assertEqual(len(self.fam.arrivals), 1)
        self.assertEqual(self.svc.family_distance_km(self.fam.family_id), 3.0)

    def test_temporary_transfer_changes_group(self):
        t1 = BASE + timedelta(hours=1)
        self.svc.apply_record(
            record("R1", self.fam.family_id, "CP1", RecordKind.TRANSFER, t1, to_batch_id="B2")
        )
        self.assertEqual(self.fam.current_batch_id, "B2")
        overview = self.svc.group_overview("B2")
        self.assertIn(self.fam.family_id, [r["family_id"] for r in overview["families"]])

    def test_withdrawal_marks_awaiting_handover(self):
        t1 = BASE + timedelta(hours=1)
        self.svc.apply_record(
            record("R1", self.fam.family_id, "CP1", RecordKind.WITHDRAWAL, t1)
        )
        self.assertTrue(self.fam.withdrawn)
        self.assertTrue(self.fam.awaiting_handover)

    def test_later_arrival_supersedes_earlier_withdrawal(self):
        # 退出登记与继续前进的记录离线冲突时，以真实时间较新者为准
        t1 = BASE + timedelta(hours=1)
        t2 = BASE + timedelta(hours=2)
        self.svc.sync_records([
            record("R2", self.fam.family_id, "CP2", RecordKind.ARRIVAL, t2),
            record("R1", self.fam.family_id, "CP1", RecordKind.WITHDRAWAL, t1),
        ])
        self.assertFalse(self.fam.withdrawn)
        self.assertFalse(self.fam.awaiting_handover)

    def test_medical_observation_flags_assistance_until_next_arrival(self):
        t1 = BASE + timedelta(hours=1)
        t2 = BASE + timedelta(hours=2)
        self.svc.apply_record(
            record("R1", self.fam.family_id, "CP1", RecordKind.MEDICAL_OBSERVATION, t1)
        )
        self.assertEqual(self.fam.status, FamilyStatus.NEEDS_ASSISTANCE)
        self.svc.apply_record(
            record("R2", self.fam.family_id, "CP2", RecordKind.ARRIVAL, t2)
        )
        self.assertEqual(self.fam.status, FamilyStatus.ON_COURSE)

    def test_checkout_at_finish(self):
        t1 = BASE + timedelta(hours=3)
        self.svc.apply_record(
            record("R1", self.fam.family_id, "CP4", RecordKind.ARRIVAL, t1)
        )
        self.svc.apply_record(
            record("R2", self.fam.family_id, "CP4", RecordKind.CHECKOUT, t1)
        )
        self.assertTrue(self.fam.checked_out)
        self.assertTrue(self.fam.awaiting_handover)


if __name__ == "__main__":
    unittest.main()
