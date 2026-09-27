"""位置披露：只向负责岗位及本家庭开放。"""

from __future__ import annotations

from .models import STAFF_ROLES, Role


def can_view_location(
    role: Role, *, viewer_family_id: str | None, target_family_id: str
) -> bool:
    """负责岗位可查任何家庭的位置，家长只能查本家庭。"""
    if role in STAFF_ROLES:
        return True
    if role == Role.家长:
        return viewer_family_id == target_family_id
    return False
