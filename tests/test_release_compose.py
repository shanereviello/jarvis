from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_release_preserves_service_boundaries_without_implicit_builds():
    definition = yaml.safe_load((ROOT / "deploy/mcp/compose.release.yml").read_text())
    assert definition["name"] == "jarvis"
    assert definition["networks"] == {"jarvis-net": {"external": True}}
    services = definition["services"]
    assert set(services) == {"jarvis-mcp", "linear-action-mcp"}
    for name, service in services.items():
        assert service["container_name"] == name
        assert service["user"] == "1000:1000"
        assert service["networks"] == ["jarvis-net"]
        assert service["pull_policy"] == "never"
        assert "image" in service and ":?" in service["image"]
        assert "build" not in service and "ports" not in service
        assert "privileged" not in service
        for mount in service["volumes"]:
            assert mount["bind"]["create_host_path"] is False
    notes = {m["source"]: m for m in services["jarvis-mcp"]["volumes"]}
    assert notes["/srv/notes/repo.git"]["read_only"] is True
    assert notes["/srv/notes/baseline"]["read_only"] is True
    assert "read_only" not in notes["/srv/notes/review"]
    assert "read_only" not in notes["/srv/jarvis/audit"]
    assert services["jarvis-mcp"]["env_file"] == ["/etc/jarvis/mcp/runtime.env"]
    linear = services["linear-action-mcp"]
    assert linear["volumes"][0]["read_only"] is True
    assert linear["volumes"][0]["source"] == "/etc/jarvis/linear/n8n_bridge_secret"
    assert "env_file" not in linear
