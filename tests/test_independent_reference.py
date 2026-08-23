
from earth_one.independent_reference import ReferenceScene, rank_reference_scenes, select_best_reference

def test_reference_rank_prefers_closest_date():
    scenes=[
        ReferenceScene("far","2025-01-20T00:00:00Z","landsat-9",10,[],{} ,{}),
        ReferenceScene("close","2025-01-15T00:00:00Z","landsat-9",50,[],{} ,{}),
    ]
    assert select_best_reference(scenes,"2025-01-14T00:00:00Z").id=="close"

def test_reference_ranking_is_deterministic():
    scenes=[
        ReferenceScene("b","2025-01-15T00:00:00Z","landsat-9",20,[],{} ,{}),
        ReferenceScene("a","2025-01-15T00:00:00Z","landsat-9",20,[],{} ,{}),
    ]
    assert [x.id for x in rank_reference_scenes(scenes,"2025-01-14T00:00:00Z")]==["a","b"]
