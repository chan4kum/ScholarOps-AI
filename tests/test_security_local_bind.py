"""Ensure dev servers default to localhost-only binding."""

from __future__ import annotations

from pathlib import Path


def test_vite_dev_server_binds_localhost_only() -> None:
    text = Path("frontend/vite.config.ts").read_text(encoding="utf-8")
    assert 'host: "127.0.0.1"' in text


def test_readme_documents_localhost_api_bind() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in text


def test_docker_compose_api_port_not_publicly_bound() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:8000:8000" in text
