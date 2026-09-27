import unittest

from safety_core import CheckpointEventKind, Role
from tests.support import add_family, at, depart, event, make_control


class LookupTest(unittest.TestCase):
    """凭标识直接对上孩子、监护人、组别和最近检查点。"""

    def setUp(self):
        self.control = make_control()
        add_family(self.control)
        depart(self.control, "FAM-092201-019")
        self.control.record_event(event("E1", "FAM-092201-019", "CP1", 30))

    def test_lookup_by_child_or_family_id(self):
        by_child = self.control.lookup("FAM-092201-019-C1")
        by_family = self.control.lookup("FAM-092201-019")
        self.assertEqual(by_child.family.family_id, by_family.family.family_id)
        self.assertEqual([c.name for c in by_child.children], ["小明"])
        self.assertEqual([g.name for g in by_child.guardians], ["张先生"])
        self.assertEqual(by_child.current_group, "中将组")
        self.assertEqual(by_child.last_checkpoint_id, "CP1")

    def test_lookup_unknown_id(self):
        with self.assertRaises(KeyError):
            self.control.lookup("不存在")


class LocationDisclosureTest(unittest.TestCase):
    """位置只向负责岗位及本家庭披露。"""

    def setUp(self):
        self.control = make_control()
        add_family(self.control)
        add_family(self.control, "FAM-092201-020")
        depart(self.control, "FAM-092201-019")
        self.control.record_event(event("E1", "FAM-092201-019", "CP1", 30))

    def test_staff_roles_see_location(self):
        for role in (Role.指挥席, Role.检查点岗位, Role.医疗岗位):
            self.assertEqual(
                self.control.location_for("FAM-092201-019", role=role), "CP1"
            )

    def test_family_sees_only_itself(self):
        self.assertEqual(
            self.control.location_for(
                "FAM-092201-019", role=Role.家长, viewer_family_id="FAM-092201-019"
            ),
            "CP1",
        )
        self.assertIsNone(
            self.control.location_for(
                "FAM-092201-019", role=Role.家长, viewer_family_id="FAM-092201-020"
            )
        )


class CommandDeskTest(unittest.TestCase):
    """指挥席关注每组最后确认点和仍未解决的事件。"""

    def test_group_status_shows_last_point_and_unresolved(self):
        control = make_control()
        add_family(control)
        add_family(control, "FAM-092201-020")
        depart(control, "FAM-092201-019")
        depart(control, "FAM-092201-020")
        control.record_event(event("E1", "FAM-092201-019", "CP1", 30))
        control.record_event(event("E2", "FAM-092201-020", "CP2", 65))
        control.record_event(
            event("E3", "FAM-092201-020", "CP2", 70, CheckpointEventKind.临时转组, to_group="慢行组")
        )
        incident = control.report_lost_child("FAM-092201-019", now=at(75))

        status = control.group_status("中将组")
        self.assertEqual([f.family_id for f in status.families], ["FAM-092201-019"])
        self.assertEqual(status.families[0].last_checkpoint_id, "CP1")
        self.assertIn(incident, status.unresolved)

        moved = control.group_status("慢行组")
        self.assertEqual([f.family_id for f in moved.families], ["FAM-092201-020"])
        self.assertEqual(moved.families[0].last_checkpoint_id, "CP2")


if __name__ == "__main__":
    unittest.main()
