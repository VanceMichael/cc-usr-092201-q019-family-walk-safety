import unittest

from safety_core import CheckpointEventKind, EventState, FamilyState, IncidentKind
from tests.support import add_family, at, depart, event, make_control


class FullJourneyTest(unittest.TestCase):
    """从出发前核验到闭赛的完整流程。"""

    def test_race_from_verification_to_close(self):
        control = make_control()
        add_family(control)  # FAM-092201-019
        add_family(control, "FAM-092201-020")

        # 出发前核验通过，分批出发
        depart(control, "FAM-092201-019")
        depart(control, "FAM-092201-020")

        # 019 正常行进并完赛
        control.record_event(event("E1", "FAM-092201-019", "CP1", 30))
        control.record_event(event("E2", "FAM-092201-019", "CP2", 70))
        control.record_event(
            event("E3", "FAM-092201-019", "CP3", 130, CheckpointEventKind.终点核销)
        )

        # 020 中途身体不适，登记医疗观察后退出
        control.record_event(event("E4", "FAM-092201-020", "CP1", 35))
        control.record_event(
            event("E5", "FAM-092201-020", "CP1", 50, CheckpointEventKind.医疗观察)
        )
        self.assertEqual(control.families["FAM-092201-020"].state, FamilyState.需协助)
        control.record_event(
            event("E6", "FAM-092201-020", "CP1", 60, CheckpointEventKind.退出)
        )

        # 退出自动触发提前结束处置，销单时完成交接
        early = control.incidents.unresolved_for_family("FAM-092201-020")
        self.assertEqual([i.kind for i in early], [IncidentKind.提前结束])
        control.resolve_incident(
            early[0].incident_id,
            resolution="监护人陪同孩子提前离场，已在检查点交接",
            now=at(65),
            handover_by="检查点岗位-01",
        )
        self.assertEqual(control.families["FAM-092201-020"].state, FamilyState.已交接)

        # 019 终点交接
        control.confirm_handover(
            "FAM-092201-019", by="终点岗位", method="终点交接", now=at(135)
        )

        # 终点未核销排查无新增，全部交接完成，允许闭赛
        self.assertEqual(control.detect_missing_finish(now=at(180)), [])
        self.assertTrue(control.close_readiness().can_close)
        control.close_event(now=at(200))
        self.assertEqual(control.event_state, EventState.已闭赛)

        # 家长留存的联络结果
        results = control.notifications.for_family("FAM-092201-020")
        self.assertTrue(any("提前结束" in n.result for n in results))


if __name__ == "__main__":
    unittest.main()
