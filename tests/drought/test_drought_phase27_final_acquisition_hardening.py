import pytest
from earth_one.drought.external_acquisition import STACDiscoveryEngine, StorageAccessType, sign_planetary_computer_url


def test_discovery_lifecycle_stays_unprobed():
    def fake_search(payload):
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "TEST_ITEM",
                    "bbox": [-94.5, 41.5, -93.5, 42.5],
                    "properties": {"datetime": "2022-07-22T16:38:49Z", "eo:cloud_cover": 1.0},
                    "assets": {k: {"href": f"https://sentinel2l2a01.blob.core.windows.net/{k}.jp2"} for k in ("B02", "B04", "B05", "B08", "B11", "SCL")},
                }
            ],
        }

    decl = STACDiscoveryEngine().search_sentinel2_granule(
        (-94.25, 41.95, -94.15, 42.05),
        "2022-07-01T00:00:00Z",
        "2022-07-31T23:59:59Z",
        custom_search_executor=fake_search,
    )
    assert decl.asset_access_records is not None
    assert len(decl.asset_access_records) == 6
    for rec in decl.asset_access_records:
        assert rec.signing_status == "NOT_YET_SIGNED"
        assert rec.access_status == "NOT_YET_PROBED"
        assert rec.raster_status == "NOT_YET_VERIFIED"
        assert rec.storage_access_type == StorageAccessType.AZURE_BLOB_SAS.value


def test_signing_is_fail_closed():
    with pytest.raises(RuntimeError, match="Fail-Closed Authorization Error"):
        sign_planetary_computer_url("https://definitely-not-a-real-sentinel-container.blob.core.windows.net/x.jp2")
