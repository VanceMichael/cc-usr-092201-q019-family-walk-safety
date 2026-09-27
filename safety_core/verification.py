"""出发前核验：家庭成员、监护授权、健康提示、批次与紧急联系人。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Family, GuardianshipAuthorization, Member, MemberKind


@dataclass(frozen=True)
class VerificationResult:
    """核验结论：是否通过，以及全部未通过项。"""

    ok: bool
    problems: tuple[str, ...]


def verify_family(
    family: Family,
    members: list[Member],
    authorizations: list[GuardianshipAuthorization],
    *,
    known_batch_ids: set[str],
) -> VerificationResult:
    """核对家庭是否具备出发条件，一次返回全部未通过项。"""
    problems: list[str] = []
    children = [m for m in members if m.kind == MemberKind.儿童]
    guardians = [m for m in members if m.kind == MemberKind.监护人]
    backups = [m for m in members if m.kind == MemberKind.备用监护人]

    if not children:
        problems.append("家庭缺少儿童成员")
    if not guardians:
        problems.append("家庭缺少随行监护人")

    authorized_adults = {m.member_id for m in guardians + backups}
    for child in children:
        covered = any(
            auth.valid
            and auth.guardian_id in authorized_adults
            and child.member_id in auth.child_ids
            for auth in authorizations
        )
        if not covered:
            problems.append(f"儿童 {child.name} 缺少有效监护授权")

    if not family.health_acknowledged:
        problems.append("健康提示尚未确认")
    if family.batch_id is None or family.batch_id not in known_batch_ids:
        problems.append("未分配有效的出发批次")
    if not family.emergency_contacts:
        problems.append("缺少紧急联系人")

    return VerificationResult(ok=not problems, problems=tuple(problems))
