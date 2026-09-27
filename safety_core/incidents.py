"""安全事件的登记与处置生命周期。"""

from __future__ import annotations

from datetime import datetime

from .models import Incident, IncidentKind, IncidentState


class IncidentDesk:
    """安全事件台账：五类触发分别建单，处置完成后销单。"""

    def __init__(self) -> None:
        self._incidents: dict[str, Incident] = {}
        self._seq = 0

    def raise_incident(
        self,
        kind: IncidentKind,
        *,
        now: datetime,
        family_id: str | None = None,
        group: str | None = None,
        detail: str = "",
    ) -> Incident:
        self._seq += 1
        incident = Incident(
            incident_id=f"INC-{self._seq:04d}",
            kind=kind,
            opened_at=now,
            family_id=family_id,
            group=group,
            detail=detail,
        )
        self._incidents[incident.incident_id] = incident
        return incident

    def resolve(self, incident_id: str, *, resolution: str, now: datetime) -> Incident:
        incident = self._incidents[incident_id]
        if incident.state == IncidentState.已解决:
            raise ValueError(f"事件 {incident_id} 已解决，不能重复销单")
        if not resolution:
            raise ValueError("销单必须填写明确的处置结果")
        incident.state = IncidentState.已解决
        incident.resolution = resolution
        incident.resolved_at = now
        return incident

    def get(self, incident_id: str) -> Incident:
        return self._incidents[incident_id]

    def unresolved(self) -> list[Incident]:
        return [i for i in self._incidents.values() if i.state == IncidentState.未解决]

    def unresolved_for_family(self, family_id: str) -> list[Incident]:
        return [i for i in self.unresolved() if i.family_id == family_id]

    def find_unresolved(self, kind: IncidentKind, family_id: str) -> Incident | None:
        for incident in self.unresolved_for_family(family_id):
            if incident.kind == kind:
                return incident
        return None

    def has_unresolved(self, kind: IncidentKind, family_id: str) -> bool:
        return self.find_unresolved(kind, family_id) is not None
