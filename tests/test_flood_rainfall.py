import pytest
from earth_one.flood_rainfall import (
    RainfallObservation,
    compute_precipitation_metrics,
    get_historical_event_rainfall,
    HISTORICAL_FLOOD_RAINFALL,
)


def test_compute_precipitation_metrics():
    series = [10.0, 50.0, 100.0, 20.0]
    obs = compute_precipitation_metrics(
        daily_series_mm=series,
        climatology_region="Bengal_Coastal",
        start_date="2020-05-18",
        end_date="2020-05-21",
        aoi_name="Test_AOI",
        latitude=22.35,
        longitude=91.38,
    )
    assert isinstance(obs, RainfallObservation)
    assert obs.accumulation_mm == 180.0
    assert obs.accumulation_window_hours == 96
    assert obs.anomaly_std == pytest.approx((180.0 - 55.0) / 45.0, rel=1e-2)
    assert obs.hours_since_peak == 24.0  # Peak was at day index 2 (100mm), 1 day from end (24h)
    assert len(obs.provenance_hash) == 64


def test_get_historical_event_rainfall():
    obs = get_historical_event_rainfall("EMSR439_Sandwip")
    assert obs.aoi_name == "EMSR439_AOI01_Sandwip_Channel"
    assert obs.accumulation_mm == pytest.approx(222.7, rel=1e-2)
    assert obs.anomaly_std > 3.0
    assert obs.hours_since_peak == 72.0


def test_unknown_event_rainfall_raises():
    with pytest.raises(KeyError):
        get_historical_event_rainfall("NON_EXISTENT_FLOOD_EVENT")
