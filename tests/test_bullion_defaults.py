from backend import bullion_defaults as bd
from backend.config import CategoryBucket


def test_returns_builtin_default_when_nothing_saved():
    assert bd.get_default_bullion_categories() == list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)


def test_save_replaces_list_and_persists():
    saved = bd.save_default_bullion_categories(["شمش طلا", "  سکه بهار آزادی  ", "", "شمش طلا"])
    assert saved == ["شمش طلا", "سکه بهار آزادی"]
    assert bd.get_default_bullion_categories() == ["شمش طلا", "سکه بهار آزادی"]


def test_saving_an_empty_list_means_nothing_preselected():
    bd.save_default_bullion_categories([])
    assert bd.get_default_bullion_categories() == []


def test_reset_reverts_to_builtin_default():
    bd.save_default_bullion_categories(["x"])
    assert bd.reset_default_bullion_categories() == list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
    assert bd.get_default_bullion_categories() == list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)


def test_corrupt_file_falls_back_to_builtin_default():
    bd._SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    bd._SETTINGS_FILE.write_text("{not json", encoding="utf-8")
    assert bd.get_default_bullion_categories() == list(CategoryBucket.DEFAULT_BULLION_CATEGORIES)
