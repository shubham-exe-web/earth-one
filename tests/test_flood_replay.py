from earth_one.flood_replay import HISTORICAL_REPLAY_EPOCHS, ReplayEpochSpec


def test_replay_epoch_specs():
    assert len(HISTORICAL_REPLAY_EPOCHS) == 3
    
    for ep in HISTORICAL_REPLAY_EPOCHS:
        assert isinstance(ep, ReplayEpochSpec)
        assert len(ep.bbox) == 4
        assert ep.s1_item.startswith("S1")
        assert ep.cop_dem_item.startswith("Copernicus")
        assert ep.jrc_gsw_item.endswith("2020")
