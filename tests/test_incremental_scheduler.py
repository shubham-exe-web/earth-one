
from earth_one.incremental_scheduler import ObservationWindow, StateLedger, schedule_new, summarize

def test_incremental_scheduler_skips_completed(tmp_path):
    ws=[
        ObservationWindow("T1","sentinel-1","2026-01-01","2026-01-31","A"),
        ObservationWindow("T1","sentinel-2","2026-01-01","2026-01-31","B"),
        ObservationWindow("T2","sentinel-1","2026-01-01","2026-01-31","C"),
    ]
    ledger=StateLedger(tmp_path/"state.json")
    ledger.mark_complete(ws[0].job_key(),{"ok":True})
    new=schedule_new(ws,ledger)
    assert len(new)==2
    assert {w.observation_key for w in new}=={"B","C"}

def test_incremental_scheduler_is_idempotent(tmp_path):
    ws=[ObservationWindow("T1","sentinel-1","2026-01-01","2026-01-31","A")]
    ledger=StateLedger(tmp_path/"state.json")
    assert len(schedule_new(ws,ledger))==1
    ledger.mark_complete(ws[0].job_key())
    assert len(schedule_new(ws,ledger))==0
    assert summarize(ws)["count"]==1
