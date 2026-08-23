from pathlib import Path


def test_s2_process_payload_shape_source_contract():
    src = Path("src/earth_one/s2_autonomous.py").read_text()

    assert '"responses": [' in src
    assert '"image/tiff"' in src

    # Earth One v2.3 eight-band Sentinel-2 contract.
    assert 'bands: 8' in src
    assert '"B11"' in src
    assert '"B12"' in src
    assert '"SCL"' in src
    assert '"dataMask"' in src

    # Legacy six-band contract must no longer be present.
    assert 'input: ["B02", "B03", "B04", "B08", "SCL", "dataMask"]' not in src

    # Legacy grouped input form must not be present.
    assert 'input: [\n      { bands: ["B02", "B03", "B04", "B08"]' not in src

    # The old REFLECTANCE-unit assertion is intentionally retained.
    assert 'units: "REFLECTANCE"' not in src
