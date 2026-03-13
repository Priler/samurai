from datetime import datetime

import ormar

from db.database import ormar_config


class SettingsAuditLog(ormar.Model):
    ormar_config = ormar_config.copy(tablename="settings_audit_log")

    id: int = ormar.Integer(primary_key=True, autoincrement=True)
    actor_id: int = ormar.BigInteger(nullable=True, index=True)
    scope_type: str = ormar.String(max_length=16, default="global")
    scope_id: int = ormar.BigInteger(nullable=True, index=True)
    key: str = ormar.String(max_length=128, index=True)
    old_value: str = ormar.Text(nullable=True)
    new_value: str = ormar.Text(nullable=True)
    created_at: datetime = ormar.DateTime(default=datetime.now)
