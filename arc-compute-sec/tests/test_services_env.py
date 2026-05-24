import os

from services.env import load_project_env


def test_load_project_env_does_not_override_existing_values(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("ARC_TEST_VALUE=from_file\n")
    monkeypatch.setenv("ARC_TEST_VALUE", "existing")

    assert load_project_env(env_path) is True
    assert os.environ["ARC_TEST_VALUE"] == "existing"


def test_load_project_env_can_override_when_requested(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("ARC_TEST_VALUE=from_file\n")
    monkeypatch.setenv("ARC_TEST_VALUE", "existing")

    assert load_project_env(env_path, override=True) is True
    assert os.environ["ARC_TEST_VALUE"] == "from_file"


def test_load_project_env_missing_file_is_false(tmp_path):
    assert load_project_env(tmp_path / ".env") is False
