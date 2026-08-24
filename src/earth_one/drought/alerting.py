from __future__ import annotations

"""Drought Module 3 Alert Lifecycle State Machine & Idempotency Engine."""

import hashlib
import time
from dataclasses import dataclass
from typing import Literal

from .events import DroughtEventRecord

DroughtAlertAction = Literal[
    "NEW_ALERT",
    "ALERT_UPDATE",
    "SEVERITY_ESCALATION",
    "SEVERITY_DEESCALATION",
    "EVENT_RESOLVED",
    "DATA_BLACKOUT_HOLD",
    "DUPLICATE_SUPPRESSED",
]


@dataclass
class DroughtAlert:
    """Standardized autonomous drought warning payload."""
    alert_id: str
    action: DroughtAlertAction
    event_id: int
    severity_tier: str
    area_ha: float
    mean_severity: float
    observability_score: float
    timestamp_epoch_days: float
    message: str
    provenance_hash: str


@dataclass
class PersistentAlertRecord:
    last_action: DroughtAlertAction
    last_severity_tier: str
    last_area_ha: float
    last_alert_timestamp_days: float
    alert_count: int


class DroughtAlertStateMachine:
    """Manages idempotent alert dispatching with hysteresis suppression and blackout safety."""

    def __init__(self, suppression_window_days: float = 14.0):
        self.suppression_window_days = suppression_window_days
        self.records: dict[int, PersistentAlertRecord] = {}

    def get_severity_tier(self, mean_sev: float) -> str:
        if mean_sev >= 0.75:
            return "EXTREME"
        elif mean_sev >= 0.60:
            return "SEVERE"
        elif mean_sev >= 0.45:
            return "MODERATE"
        return "MILD"

    def process_event_alert(
        self,
        event: DroughtEventRecord,
        current_time_days: float,
        is_data_blackout: bool = False,
    ) -> DroughtAlert:
        """Evaluate event against persistent alert history and return safe action."""
        ev_id = event.event_id

        # 1. Fail-Safe Blackout Hold
        if is_data_blackout:
            prov = hashlib.sha256(f"BLACKOUT_{ev_id}_{current_time_days}".encode()).hexdigest()
            return DroughtAlert(
                alert_id=f"ALT-DR-BLACKOUT-{ev_id}",
                action="DATA_BLACKOUT_HOLD",
                event_id=ev_id,
                severity_tier="UNKNOWN",
                area_ha=event.area_expected_ha,
                mean_severity=0.0,
                observability_score=0.0,
                timestamp_epoch_days=current_time_days,
                message="Telemetry blackout detected: holding alert status without false all-clear.",
                provenance_hash=prov,
            )

        sev_tier = self.get_severity_tier(event.mean_severity)

        # 2. New Alert
        if ev_id not in self.records:
            self.records[ev_id] = PersistentAlertRecord(
                last_action="NEW_ALERT",
                last_severity_tier=sev_tier,
                last_area_ha=event.area_expected_ha,
                last_alert_timestamp_days=current_time_days,
                alert_count=1,
            )
            prov = hashlib.sha256(f"NEW_ALT_{ev_id}_{sev_tier}_{current_time_days}".encode()).hexdigest()
            return DroughtAlert(
                alert_id=f"ALT-DR-{ev_id}-001",
                action="NEW_ALERT",
                event_id=ev_id,
                severity_tier=sev_tier,
                area_ha=event.area_expected_ha,
                mean_severity=event.mean_severity,
                observability_score=event.mean_observability,
                timestamp_epoch_days=current_time_days,
                message=f"NEW DROUGHT WARNING: {sev_tier} water stress covering {event.area_expected_ha:.1f} ha.",
                provenance_hash=prov,
            )

        # 3. Existing Alert Evaluation
        rec = self.records[ev_id]
        time_elapsed = current_time_days - rec.last_alert_timestamp_days

        # Check for Escalation
        tier_ranks = {"MILD": 1, "MODERATE": 2, "SEVERE": 3, "EXTREME": 4}
        if tier_ranks.get(sev_tier, 0) > tier_ranks.get(rec.last_severity_tier, 0):
            action: DroughtAlertAction = "SEVERITY_ESCALATION"
        elif tier_ranks.get(sev_tier, 0) < tier_ranks.get(rec.last_severity_tier, 0):
            action = "SEVERITY_DEESCALATION"
        elif time_elapsed < self.suppression_window_days:
            # Duplicate suppression
            prov = hashlib.sha256(f"SUPP_{ev_id}_{current_time_days}".encode()).hexdigest()
            return DroughtAlert(
                alert_id=f"ALT-DR-{ev_id}-{rec.alert_count}",
                action="DUPLICATE_SUPPRESSED",
                event_id=ev_id,
                severity_tier=sev_tier,
                area_ha=event.area_expected_ha,
                mean_severity=event.mean_severity,
                observability_score=event.mean_observability,
                timestamp_epoch_days=current_time_days,
                message=f"Alert suppressed: within {self.suppression_window_days}d hysteresis window.",
                provenance_hash=prov,
            )
        else:
            action = "ALERT_UPDATE"

        # Update record
        rec.last_action = action
        rec.last_severity_tier = sev_tier
        rec.last_area_ha = event.area_expected_ha
        rec.last_alert_timestamp_days = current_time_days
        rec.alert_count += 1

        prov = hashlib.sha256(f"UPD_{ev_id}_{action}_{current_time_days}".encode()).hexdigest()
        return DroughtAlert(
            alert_id=f"ALT-DR-{ev_id}-{rec.alert_count:03d}",
            action=action,
            event_id=ev_id,
            severity_tier=sev_tier,
            area_ha=event.area_expected_ha,
            mean_severity=event.mean_severity,
            observability_score=event.mean_observability,
            timestamp_epoch_days=current_time_days,
            message=f"DROUGHT {action}: {sev_tier} water stress across {event.area_expected_ha:.1f} ha.",
            provenance_hash=prov,
        )
