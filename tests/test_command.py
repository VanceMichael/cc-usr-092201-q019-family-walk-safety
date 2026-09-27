import unittest
from datetime import timedelta

from safety_ops import EventStatus, FamilyStatus, IncidentType, RecordKind, StaffRole
from support import BASE, build_service, make_family, record


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.svc, _ = build_service()
        self.f1 = make_family(family_id="FAM-1")
        self.f2 = make_family(family_id="FAM-2")
        for fam in (self.f1, self.f2):
            self.svc.register_family(fam)
            self.svc.depart_family(fam.family_id)

    def _arrive(self, fam, cp, hours):
        self.svc.apply_record(
            record(f"ARR-{fam.family_id}-{cp}", fam.family_id, cp, RecordKind.ARRIVAL,
                   BASE + timedelta(hours=hours))
        )

    def test_group_overview_shows_last_confirmed_and_trailing_point(self):
        self._arrive(self.f1, "CP3", 2)
        self._arrive(self.f2, "CP1", 1)
        overview = self.svc.group_overview("B1")
        self.assertEqual(overview["trailing_checkpoint"], "滨江步道")
        rows = {r["family_id"]: r for r in overview["families"]}
        self.assertEqual(rows["FAM-1"]["last_checkpoint"], "城市阳台")
        self.assertEqual(rows["FAM-2"]["last_checkpoint"], "滨江步道")

    def test_group_overview_lists_unresolved_incidents(self):
        inc = self.svc.open_incident(IncidentType.LOST_CHILD, family_id="FAM-1")
        overview = self.svc.group_overview("B1")
        self.assertIn(inc.incident_id, overview["unresolved_incidents"])

    def test_close_blocked_until_everyone_handed_over(self):
        self._arrive(self.f1, "CP4", 3)
        self._arrive(self.f2, "CP4", 3)
        # 即使全部到达终点，未完成交接也不允许闭赛
        with self.assertRaises(ValueError):
            self.svc.close_event()
        self.svc.confirm_handover("FAM-1", "FAM-1-G1", StaffRole.CHECKPOINT)
        with self.assertRaises(ValueError):
            self.svc.close_event()
        self.svc.confirm_handover("FAM-2", "FAM-2-G1", StaffRole.CHECKPOINT)
        self.svc.close_event()
        self.assertEqual(self.svc.event_status, EventStatus.CLOSED)

    def test_close_blocked_by_unresolved_incident(self):
        self.svc.open_incident(IncidentType.LOST_CHILD, family_id="FAM-1")
        self.svc.confirm_handover("FAM-1", "FAM-1-G1", StaffRole.CHECKPOINT)
        self.svc.confirm_handover("FAM-2", "FAM-2-G1", StaffRole.CHECKPOINT)
        with self.assertRaises(ValueError):
            self.svc.close_event()

    def test_finish_count_alone_does_not_close_event(self):
        # 看到完赛数字（已核销）不等于完成安全交接
        for fam in (self.f1, self.f2):
            self._arrive(fam, "CP4", 3)
            self.svc.apply_record(
                record(f"CO-{fam.family_id}", fam.family_id, "CP4", RecordKind.CHECKOUT,
                       BASE + timedelta(hours=3, minutes=1))
            )
        with self.assertRaises(ValueError):
            self.svc.close_event()

    def test_parent_receives_handover_notification(self):
        self.svc.confirm_handover("FAM-1", "FAM-1-G1", StaffRole.CHECKPOINT)
        notes = self.svc.family_notifications("FAM-1")
        self.assertTrue(any("安全交接" in n.message for n in notes))
        self.assertEqual(self.f1.status, FamilyStatus.HANDED_OVER)


if __name__ == "__main__":
    unittest.main()
