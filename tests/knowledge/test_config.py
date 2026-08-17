from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Config


def _load_config(config_path: Path) -> Config:
    """Load a fresh Config instance from a test TOML file."""
    loaded_config = object.__new__(Config)
    loaded_config._get_config_path = lambda: config_path
    loaded_config._config = None
    loaded_config._load_initial_config()
    return loaded_config


def _write_base_config(config_path: Path, knowledge: str = "") -> None:
    config_path.write_text(
        """
[llm]
model = "test-model"
base_url = "http://localhost"
api_key = "test-key"
api_type = "openai"
api_version = ""
""".strip()
        + "\n"
        + knowledge,
        encoding="utf-8",
    )


def test_knowledge_settings_are_disabled_by_default(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_base_config(config_path)

    loaded_config = _load_config(config_path)

    assert loaded_config.knowledge.enabled is False
    assert loaded_config.knowledge.qdrant_url == "http://127.0.0.1:6333"
    assert loaded_config.knowledge.collection_name == "solvex_papers"
    assert loaded_config.knowledge.dense_model == "intfloat/multilingual-e5-large"
    assert loaded_config.knowledge.sparse_model == "Qdrant/bm25"
    assert loaded_config.knowledge.default_top_k == 6


def test_knowledge_settings_read_explicit_toml_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_base_config(
        config_path,
        """
[knowledge]
enabled = true
qdrant_url = "http://qdrant.internal:6333"
collection_name = "competition_papers"
dense_model = "custom/e5"
sparse_model = "custom/bm25"
default_top_k = 9
""".lstrip(),
    )

    loaded_config = _load_config(config_path)

    assert loaded_config.knowledge.enabled is True
    assert loaded_config.knowledge.qdrant_url == "http://qdrant.internal:6333"
    assert loaded_config.knowledge.collection_name == "competition_papers"
    assert loaded_config.knowledge.dense_model == "custom/e5"
    assert loaded_config.knowledge.sparse_model == "custom/bm25"
    assert loaded_config.knowledge.default_top_k == 9


def test_knowledge_settings_reject_default_top_k_above_tool_limit(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    _write_base_config(
        config_path,
        """
[knowledge]
default_top_k = 13
""".lstrip(),
    )

    with pytest.raises(ValidationError, match="default_top_k"):
        _load_config(config_path)


def test_config_constructor_loads_default_knowledge_settings(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    _write_base_config(config_path)
    original_instance = Config._instance
    original_initialized = Config._initialized
    monkeypatch.setattr(Config, "_get_config_path", staticmethod(lambda: config_path))

    try:
        Config._instance = None
        Config._initialized = False
        loaded_config = Config()
    finally:
        Config._instance = original_instance
        Config._initialized = original_initialized

    assert loaded_config.knowledge.enabled is False
    assert loaded_config.knowledge.collection_name == "solvex_papers"
