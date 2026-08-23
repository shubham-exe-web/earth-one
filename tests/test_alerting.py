
import os, json
from earth_one.alerting import Alert, alert_from_execution

def test_execution_success_alert():
    a=alert_from_execution({"jobs_submitted":3,"summary":{"SUCCEEDED":3,"FAILED":0,"PLANNED":0}})
    assert a.severity=="success"
    assert "3 job" in a.title

def test_execution_failure_alert():
    a=alert_from_execution({"jobs_submitted":3,"summary":{"SUCCEEDED":2,"FAILED":1,"PLANNED":0}})
    assert a.severity=="critical"
    assert a.details["failed"]==1

def test_dry_run_alert():
    a=alert_from_execution({"jobs_submitted":3,"summary":{"PLANNED":3}})
    assert a.severity=="info"
    assert "planned" in a.title.lower()

def test_custom_finding():
    from earth_one.alerting import alert_from_finding
    a=alert_from_finding("Flood candidate","Candidate event detected",{"tile":"T1","score":0.93})
    assert a.severity=="finding"
    assert a.details["score"]==0.93
