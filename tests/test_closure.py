import unittest

from safety_core import CheckpointEventKind, EventState
from tests.support import add_family, at, depart, event, make_control


class ClosureTest(unittest.TestCase):
    """全部人员完成安全交接才允许闭赛。"""

    def setUp(self):
        self.control = make_control()
        add_family(self.control)
        depart(self.control, "FAM-092201-019")

    def test_finish_count_alone_does_not_close_event(self):
        # 终点已核销，但没有交接确认，仍不能闭赛
        self.control.record_event(
            event("E1", "FAM-092201-019", "CP3", 130, CheckpointEventKind.终点核销)
        )
        readiness = self.control.close_readiness()
        self.assertFalse(readiness.can_close)
        self.assertIn("FAM-092201-019", readiness.pending_families)
        with self.assertRaises(RuntimeError):
            self.control.close_event(now=at(200))

    def test_unresolved_incident_blocks_closure(self):
        self.control.confirm_handover(
            "FAM-092201-019", by="终点岗位", method="终点交接", now=at(140)
        )
        incident = self.control.report_lost_child("FAM-092201-019", now=at(150))
        readiness = self.control.close_readiness()
        self.assertFalse(readiness.can_close)
        self.assertIn(incident.incident_id, readiness.unresolved_incidents)

    def test_close_after_all_handovers(self):
        self.control.record_event(
            event("E1", "FAM-092201-019", "CP3", 130, CheckpointEventKind.终点核销)
        )
        self.control.confirm_handover(
            "FAM-092201-019", by="终点岗位", method="终点交接", now=at(140)
        )
        add_family(self.control, "FAM-092201-099")  # 未出发的家庭不阻碍闭赛
        self.assertTrue(self.control.close_readiness().can_close)
        self.control.close_event(now=at(200))
        self.assertEqual(self.control.event_state, EventState.已闭赛)


if __name__ == "__main__":
    unittest.main()
