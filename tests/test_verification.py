import unittest

from safety_core import FamilyState
from tests.support import add_family, at, make_control


class VerificationTest(unittest.TestCase):
    """出发前核验：全部条件通过才允许出发。"""

    def setUp(self):
        self.control = make_control()

    def test_complete_family_departs(self):
        add_family(self.control)
        result = self.control.verify_family("FAM-092201-019")
        self.assertTrue(result.ok)
        self.control.depart("FAM-092201-019", now=at(0))
        self.assertEqual(
            self.control.families["FAM-092201-019"].state, FamilyState.已出发
        )

    def test_missing_authorization_blocks_departure(self):
        add_family(self.control, with_authorization=False)
        result = self.control.verify_family("FAM-092201-019")
        self.assertFalse(result.ok)
        self.assertTrue(any("监护授权" in p for p in result.problems))
        with self.assertRaises(ValueError):
            self.control.depart("FAM-092201-019", now=at(0))

    def test_health_contact_and_batch_are_required(self):
        add_family(
            self.control, health_acknowledged=False, with_contact=False, batch_id=None
        )
        result = self.control.verify_family("FAM-092201-019")
        self.assertFalse(result.ok)
        self.assertTrue(any("健康提示" in p for p in result.problems))
        self.assertTrue(any("紧急联系人" in p for p in result.problems))
        self.assertTrue(any("批次" in p for p in result.problems))


if __name__ == "__main__":
    unittest.main()
