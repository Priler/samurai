"""
Enums for consistent type checking across the codebase.
"""
from enum import Enum


class MemberStatus(str, Enum):
    """Telegram chat member status values."""
    CREATOR = "creator"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"
    LEFT = "left"
    KICKED = "kicked"
    
    @classmethod
    def is_admin(cls, status: str) -> bool:
        """Check if status is admin or creator."""
        return status in (cls.ADMINISTRATOR, cls.CREATOR)
    
    @classmethod
    def admin_statuses(cls) -> tuple:
        """Return tuple of admin statuses for 'in' checks."""
        return (cls.ADMINISTRATOR.value, cls.CREATOR.value)
