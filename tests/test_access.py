import unittest
from datetime import timedelta

from safety_ops import RecordKind, StaffRole, Viewer, location_view
from support import BASE, build_service, make_family, record


class AccessTest(unittest.TestCase):
    def setUp(self):
        self.svc, _ = build_service()
        self.fam = make_family()
        self.svc.register_family(self.fam)
        self.svc.depart_family(self.fam.family_id)
        self.svc.apply_record(
            record("R1", self.fam.family_id, "CP1", RecordKind.ARRIVAL,
                   BASE + timedelta(hours=1))
        )

    def test_responsible_staff_see_location(self):
        for role in (StaffRole.COMMAND, StaffRole.CHECKPOINT, StaffRole.MEDICAL):
            view = location_view(self.svc, self.fam.family_id, Viewer(role=role))
            self.assertIsNotNone(view)
            self.assertEqual(view.last_checkpoint, "滨江步道")
            self.assertEqual(view.distance_km, 3.0)

    def test_own_family_sees_location(self):
        view = location_view(
            self.svc, self.fam.family_id, Viewer(family_id=self.fam.family_id)
        )
        self.assertIsNotNone(view)
        self.assertEqual(view.last_checkpoint, "滨江步道")

    def test_other_family_cannot_see_location(self):
        view = location_view(
            self.svc, self.fam.family_id, Viewer(family_id="FAM-OTHER")
        )
        self.assertIsNone(view)

    def test_anonymous_cannot_see_location(self):
        self.assertIsNone(location_view(self.svc, self.fam.family_id, Viewer()))


if __name__ == "__main__":
    unittest.main()
