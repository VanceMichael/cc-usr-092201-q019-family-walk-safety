import unittest

from safety_core import CheckpointEventKind, FamilyState, IncidentKind
from tests.support import add_family, at, depart, event, make_control


class IncidentTest(unittest.TestCase):
    """五类触发分别进入处置流程，家长收到明确联络结果。"""

    def setUp(self):
        self.control = make_control()
        add_family(self.control, with_backup_guardian=True)
        depart(self.control, "FAM-092201-019")
        self.control.record_event(event("E1", "FAM-092201-019", "CP1", 30))

    def test_lost_child_flow(self):
        incident = self.control.report_lost_child("FAM-092201-019", now=at(40))
        self.assertEqual(incident.kind, IncidentKind.儿童走散)
        self.assertEqual(
            self.control.families["FAM-092201-019"].state, FamilyState.需协助
        )
        self.assertIn(incident, self.control.incidents.unresolved())

        self.control.resolve_incident(
            incident.incident_id,
            resolution="孩子已在水间留趣检查点与监护人会合",
            now=at(55),
        )
        self.assertEqual(
            self.control.families["FAM-092201-019"].state, FamilyState.行进中
        )
        results = self.control.notifications.for_family("FAM-092201-019")
        self.assertTrue(any("会合" in n.result for n in results))

    def test_backup_guardian_must_be_authorized(self):
        with self.assertRaises(ValueError):
            self.control.request_backup_guardian_pickup(
                "FAM-092201-019", "FAM-092201-019-G1", now=at(40)
            )
        with self.assertRaises(ValueError):
            self.control.request_backup_guardian_pickup(
                "FAM-092201-019", "STRANGER", now=at(40)
            )

    def test_backup_guardian_pickup_completes_with_handover(self):
        incident = self.control.request_backup_guardian_pickup(
            "FAM-092201-019", "FAM-092201-019-B1", now=at(40)
        )
        with self.assertRaises(ValueError):
            self.control.resolve_incident(
                incident.incident_id, resolution="已接回", now=at(50)
            )
        self.control.resolve_incident(
            incident.incident_id,
            resolution="备用监护人已接回孩子",
            now=at(50),
            handover_by="FAM-092201-019-B1",
        )
        self.assertEqual(
            self.control.handovers["FAM-092201-019"].method, "备用监护人接回"
        )
        self.assertEqual(
            self.control.families["FAM-092201-019"].state, FamilyState.已交接
        )

    def test_missing_finish_sweep(self):
        add_family(self.control, "FAM-092201-020")
        depart(self.control, "FAM-092201-020")
        self.control.record_event(
            event("E9", "FAM-092201-020", "CP3", 130, CheckpointEventKind.终点核销)
        )
        raised = self.control.detect_missing_finish(now=at(180))
        self.assertEqual([i.family_id for i in raised], ["FAM-092201-019"])
        again = self.control.detect_missing_finish(now=at(190))
        self.assertEqual(again, [])  # 不重复建单

    def test_route_closure_notifies_affected_families(self):
        incident = self.control.close_route(
            now=at(45), group="中将组", detail="前方栈道临时封闭"
        )
        self.assertEqual(incident.kind, IncidentKind.路线封闭)
        results = self.control.notifications.for_family("FAM-092201-019")
        self.assertTrue(any("路线封闭" in n.result for n in results))
        self.control.resolve_incident(
            incident.incident_id, resolution="栈道已重开", now=at(80)
        )
        results = self.control.notifications.for_family("FAM-092201-019")
        self.assertTrue(any("已重开" in n.result for n in results))


if __name__ == "__main__":
    unittest.main()
