
from pathlib import Path
import os, json
from earth_one.runtime_config import env_status, load_env_file
from earth_one.service import configured

def test_env_status_is_false_without_secrets(monkeypatch):
    for k in [
        "CDSE_CLIENT_ID","CDSE_CLIENT_SECRET","EARTH_ONE_SMTP_HOST",
        "EARTH_ONE_SMTP_USERNAME","EARTH_ONE_SMTP_PASSWORD",
        "EARTH_ONE_ALERT_FROM","EARTH_ONE_ALERT_TO"
    ]:
        monkeypatch.delenv(k, raising=False)
    s=env_status()
    assert all(v is False for v in s.values())
    assert configured() is False

def test_env_file_loader(tmp_path, monkeypatch):
    p=tmp_path/"earth_one.env"
    p.write_text('CDSE_CLIENT_ID="abc"\nCDSE_CLIENT_SECRET="secret"\n',encoding="utf-8")
    monkeypatch.delenv("CDSE_CLIENT_ID",raising=False)
    monkeypatch.delenv("CDSE_CLIENT_SECRET",raising=False)
    assert load_env_file(p)==p
    assert os.environ["CDSE_CLIENT_ID"]=="abc"
    assert os.environ["CDSE_CLIENT_SECRET"]=="secret"
