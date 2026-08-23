
from __future__ import annotations

"""Earth One notification policy."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationPolicy:
    alert_on_failure: bool = True
    alert_on_success: bool = True
    alert_on_finding: bool = True
    alert_on_validation_failure: bool = True
    attach_reports: bool = True


DEFAULT_POLICY=NotificationPolicy()
