"""Tests for CLI workspace directory resolution.

Regression coverage for #90: ``workspace_dir`` configured in ``config.yaml``
must be honoured when no ``--workspace`` CLI argument is provided.
"""

import os
from pathlib import Path

import pytest

from mini_agent.cli import resolve_workspace_dir
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig


def _make_config(workspace_dir: str) -> Config:
    """Build a minimal :class:`Config` for tests with a custom workspace."""
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=workspace_dir),
        tools=ToolsConfig(),
    )


def test_resolve_workspace_prefers_cli_argument(tmp_path: Path) -> None:
    """When ``--workspace`` is provided it wins over ``config.workspace_dir``."""
    cli_dir = tmp_path / "from-cli"
    config_dir = tmp_path / "from-config"
    config = _make_config(str(config_dir))

    resolved = resolve_workspace_dir(str(cli_dir), config)

    assert resolved == cli_dir.resolve()


def test_resolve_workspace_falls_back_to_config(tmp_path: Path) -> None:
    """Without a CLI argument the value from ``config.yaml`` is used."""
    config_dir = tmp_path / "from-config"
    config = _make_config(str(config_dir))

    resolved = resolve_workspace_dir(None, config)

    assert resolved == config_dir.resolve()


def test_resolve_workspace_relative_config_resolves_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relative ``workspace_dir`` from config resolves against the current cwd.

    Reproduces the scenario from issue #90 where users set
    ``workspace_dir: "./workspace"`` and expect ``<cwd>/workspace`` to be used.
    """
    monkeypatch.chdir(tmp_path)
    config = _make_config("./workspace")

    resolved = resolve_workspace_dir(None, config)

    assert resolved == (tmp_path / "workspace").resolve()


def test_resolve_workspace_falls_back_to_cwd_when_config_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty ``workspace_dir`` in config falls back to the current cwd."""
    monkeypatch.chdir(tmp_path)
    config = _make_config("")

    resolved = resolve_workspace_dir(None, config)

    assert resolved == tmp_path


def test_resolve_workspace_expands_user_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``~`` in ``workspace_dir`` is expanded to the user home directory."""
    fake_home = tmp_path / "home" / "user"
    fake_home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    # On Windows ``Path.expanduser`` honours USERPROFILE, set both to be safe.
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    config = _make_config("~/my-workspace")

    resolved = resolve_workspace_dir(None, config)

    assert resolved == (fake_home / "my-workspace").resolve()
