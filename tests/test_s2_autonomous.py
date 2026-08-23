from earth_one.s2_autonomous import S2Scene, select_best_s2, _evalscript

def scene(pid,date,cloud):
    return S2Scene(pid,pid,date,"S2B",cloud,[0,0,1,1],None,{},{})

def test_select_best_scene():
    xs=[scene("FAR","2026-01-10T10:00:00Z",1),scene("CLOSE","2026-01-01T10:00:00Z",30),scene("CLOSELOWCC","2026-01-01T11:00:00Z",10)]
    assert select_best_s2(xs,"2026-01-01T00:00:00Z").product_id=="CLOSE"

def test_evalscript_contains_exact_scene_filter():
    e=_evalscript("S2B_TEST_PRODUCT")
    assert "sentinel2ProductId ===" in e
    assert "S2B_TEST_PRODUCT" in e
    assert '"SCL"' in e

def test_selection_deterministic():
    xs=[scene("B","2026-01-01T10:00:00Z",20),scene("A","2026-01-01T10:00:00Z",20)]
    assert select_best_s2(xs,"2026-01-01T10:00:00Z").product_id=="A"
