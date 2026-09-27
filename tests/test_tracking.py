import unittest

from safety_core import CheckpointEventKind, FamilyState
from tests.support import add_family, depart, event, make_control


class OfflineMergeTest(unittest.TestCase):
    """检查点离线登记，联网后依真实时间合并而不重复计程。"""

    def setUp(self):
        self.control = make_control()
        add_family(self.control)
        depart(self.control, "FAM-092201-019")

    def test_offline_events_merge_by_real_time(self):
        # 两台设备离线记录，联网后乱序上传
        first = self.control.sync_events(
            [
                event("E3", "FAM-092201-019", "CP2", 60),
                event("E1", "FAM-092201-019", "CP1", 30),
            ]
        )
        self.assertEqual(len(first), 2)
        second = self.control.sync_events(
            [
                event("E2", "FAM-092201-019", "CP1", 20),  # 更早的到达，补传
                event("E4", "FAM-092201-019", "CP3", 120, CheckpointEventKind.终点核销),
            ]
        )
        self.assertEqual(len(second), 2)
        progress = self.control.progress("FAM-092201-019")
        self.assertEqual(progress.last_checkpoint_id, "CP3")
        self.assertEqual(progress.distance_km, 13.5)
        self.assertTrue(progress.finished)

    def test_resync_does_not_double_count(self):
        batch = [
            event("E1", "FAM-092201-019", "CP1", 30),
            event("E2", "FAM-092201-019", "CP2", 60),
        ]
        self.control.sync_events(batch)
        again = self.control.sync_events(batch)  # 同一批离线记录重复上传
        self.assertEqual(again, [])
        progress = self.control.progress("FAM-092201-019")
        self.assertEqual(progress.distance_km, 9.0)  # 里程只计一次

    def test_transfer_and_medical_observation(self):
        self.control.sync_events(
            [
                event("E1", "FAM-092201-019", "CP1", 30),
                event("E2", "FAM-092201-019", "CP1", 35, CheckpointEventKind.医疗观察),
            ]
        )
        progress = self.control.progress("FAM-092201-019")
        self.assertTrue(progress.under_medical_observation)
        self.assertEqual(
            self.control.families["FAM-092201-019"].state, FamilyState.需协助
        )

        self.control.sync_events(
            [
                event("E3", "FAM-092201-019", "CP2", 70),
                event("E4", "FAM-092201-019", "CP2", 75, CheckpointEventKind.临时转组, to_group="慢行组"),
            ]
        )
        progress = self.control.progress("FAM-092201-019")
        self.assertFalse(progress.under_medical_observation)
        self.assertEqual(progress.current_group, "慢行组")
        self.assertEqual(progress.distance_km, 9.0)


if __name__ == "__main__":
    unittest.main()
