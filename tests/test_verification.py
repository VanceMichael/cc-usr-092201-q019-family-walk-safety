import unittest

from safety_ops import FamilyStatus
from support import build_service, make_family


class VerificationTest(unittest.TestCase):
    def setUp(self):
        self.svc, _ = build_service()

    def test_ready_family_departs(self):
        fam = make_family()
        self.svc.register_family(fam)
        self.assertEqual(self.svc.verify_family(fam.family_id), [])
        self.svc.depart_family(fam.family_id)
        self.assertEqual(fam.status, FamilyStatus.DEPARTED)

    def test_missing_emergency_contact_blocks_departure(self):
        fam = make_family()
        fam.emergency_contacts = []
        self.svc.register_family(fam)
        problems = self.svc.verify_family(fam.family_id)
        self.assertTrue(any("紧急联系人" in p for p in problems))
        with self.assertRaises(ValueError):
            self.svc.depart_family(fam.family_id)
        self.assertEqual(fam.status, FamilyStatus.PENDING)

    def test_missing_guardian_authorization_blocks_departure(self):
        fam = make_family()
        fam.authorizations = []
        self.svc.register_family(fam)
        problems = self.svc.verify_family(fam.family_id)
        self.assertTrue(any("监护授权" in p for p in problems))

    def test_unreviewed_health_notes_block_departure(self):
        fam = make_family()
        fam.members[0].health_reviewed = False
        self.svc.register_family(fam)
        problems = self.svc.verify_family(fam.family_id)
        self.assertTrue(any("健康提示" in p for p in problems))

    def test_missing_batch_blocks_departure(self):
        fam = make_family(batch_id=None)
        self.svc.register_family(fam)
        problems = self.svc.verify_family(fam.family_id)
        self.assertTrue(any("批次" in p for p in problems))

    def test_double_departure_rejected(self):
        fam = make_family()
        self.svc.register_family(fam)
        self.svc.depart_family(fam.family_id)
        with self.assertRaises(ValueError):
            self.svc.depart_family(fam.family_id)


if __name__ == "__main__":
    unittest.main()
