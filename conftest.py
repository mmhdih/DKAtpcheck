import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_settings(tmp_path, monkeypatch):
    """Never read or write the real ~/.atp_analyzer settings while testing."""
    from backend import bullion_defaults as bd
    from backend import field_names as fn

    settings_dir = tmp_path / ".atp_analyzer"
    monkeypatch.setattr(fn, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(fn, "_SETTINGS_FILE", settings_dir / "field_names.json")
    monkeypatch.setattr(bd, "_SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(bd, "_SETTINGS_FILE", settings_dir / "bullion_categories.json")
    yield
