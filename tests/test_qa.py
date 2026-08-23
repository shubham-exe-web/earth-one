import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from earth_one.qa import inspect_file


def test_file_qa(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"earth-one")
    qa = inspect_file(p)
    assert qa.exists
    assert qa.readable
    assert qa.bytes == 9
    assert qa.sha256
