def test_s1_module_contains_fstring_evalscript():
    from pathlib import Path

    src = Path("src/earth_one/s1_autonomous.py").read_text()

    assert "evalscript = f'''//VERSION=3" in src
    assert ".format(" not in src[
        src.find("def process_exact_scene"):
        src.find("def process_exact_scene") + 5000
    ]

    # Dynamic output contract inside Python f-string.
    assert 'output: {{ id: "default", bands: {nbands}' in src

    # Dynamic polarization insertion and dataMask.
    assert 'input: [{inputs}, "dataMask"]' in src
    assert "return [{returns}, s.dataMask];" in src

    # Operational defaults remain dual-polarization.
    assert 'polarizations or ["VV", "VH"]' in src
