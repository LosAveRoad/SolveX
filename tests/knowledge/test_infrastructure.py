from pathlib import Path

import yaml


def test_qdrant_healthcheck_uses_a_shell_tcp_probe_without_curl() -> None:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.knowledge.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    healthcheck = compose["services"]["qdrant"]["healthcheck"]

    assert healthcheck["test"][0] == "CMD-SHELL"
    command = healthcheck["test"][1]
    assert "curl" not in command
    assert "timeout 5" in command
    assert "bash -c" in command
    assert "/dev/tcp/127.0.0.1/6333" in command
