from dataclasses import dataclass
from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    root: Path
    config: dict

    @classmethod
    def load(cls, path: str = "config.yaml"):
        root = Path.cwd()
        cfg_path = root / path
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cls(root=root, config=cfg)

    @property
    def stac_endpoint(self) -> str:
        return self.config["stac"]["endpoint"].rstrip("/")

    @property
    def state_db(self) -> Path:
        return self.root / self.config["system"]["state_db"]

    @property
    def manifest_dir(self) -> Path:
        return self.root / self.config["system"]["manifest_dir"]

    @property
    def timeout(self) -> int:
        return int(self.config["acquisition"]["request_timeout_seconds"])
