
from earth_one.global_orchestration import (
    global_scope, make_scope, tile_scope, build_jobs, partition_jobs, stable_job_id
)

def test_global_scope_is_valid():
    s=global_scope()
    s.validate()
    assert s.bbox == (-180.0,-90.0,180.0,90.0)

def test_aoi_tiles_are_deterministic():
    s=make_scope("TEST","aoi",[0,0,10,10])
    a=tile_scope(s,5,5)
    b=tile_scope(s,5,5)
    assert [x.tile_id for x in a]==[x.tile_id for x in b]
    assert len(a)==4

def test_global_job_sharding_is_restartable():
    s=make_scope("TEST","aoi",[0,0,10,10])
    jobs=build_jobs(s,["sentinel-1","sentinel-2"],"monitor","2025-01-01","2025-01-31",5,5)
    assert len(jobs)==8
    shards=[partition_jobs(jobs,3,i) for i in range(3)]
    ids=[j.job_id for sh in shards for j in sh]
    assert len(ids)==len(set(ids))==8
    assert sorted(ids)==sorted(j.job_id for j in jobs)

def test_job_id_is_stable():
    a=stable_job_id("T:0000:0000","sentinel-1","monitor","2025","2026")
    b=stable_job_id("T:0000:0000","sentinel-1","monitor","2025","2026")
    assert a==b
