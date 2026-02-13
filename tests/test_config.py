"""Tests for configuration module."""

import json
from pathlib import Path

import pytest

from mcp_fess.config import (
    ContentFetchConfig,
    DomainConfig,
    HttpTransportConfig,
    LimitsConfig,
    LoggingConfig,
    SecurityConfig,
    ServerConfig,
    TimeoutsConfig,
    load_config,
)


def test_domain_config():
    """Test domain configuration."""
    domain = DomainConfig(
        id="test", name="Test Domain", description="Test", labelFilter="test_label"
    )
    assert domain.id == "test"
    assert domain.name == "Test Domain"
    assert domain.labelFilter == "test_label"


def test_http_transport_config_defaults():
    """Test HTTP transport configuration defaults."""
    config = HttpTransportConfig()
    assert config.bindAddress == "127.0.0.1"
    assert config.port == 0
    assert config.path == "/mcp"
    assert config.enableSse is True


def test_timeouts_config_defaults():
    """Test timeout configuration defaults."""
    config = TimeoutsConfig()
    assert config.fessRequestTimeoutMs == 30000
    assert config.longRunningThresholdMs == 2000


def test_limits_config_defaults():
    """Test limits configuration defaults."""
    config = LimitsConfig()
    assert config.maxPageSize == 100
    assert config.maxChunkBytes == 262144
    assert config.maxInFlightRequests == 32


def test_logging_config_defaults():
    """Test logging configuration defaults."""
    config = LoggingConfig()
    assert config.level == "info"
    assert config.retainDays == 7


def test_security_config_defaults():
    """Test security configuration defaults."""
    config = SecurityConfig()
    assert config.httpAuthToken is None
    assert config.allowNonLocalhostBind is False


def test_content_fetch_config_defaults():
    """Test content fetch configuration defaults."""
    config = ContentFetchConfig()
    assert config.enabled is True
    assert config.maxBytes == 5 * 1024 * 1024
    assert config.timeoutMs == 20000
    assert config.allowedSchemes == ["http", "https"]
    assert config.allowPrivateNetworkTargets is False
    assert config.userAgent == "MCP-Fess/1.0"
    assert config.enablePdf is False


def test_server_config_validation():
    """Test server configuration validation."""
    config_data = {
        "fessBaseUrl": "http://localhost:8080/",
        "domain": {
            "id": "test",
            "name": "Test",
            "labelFilter": "test",
        },
    }
    config = ServerConfig(**config_data)
    assert config.fessBaseUrl == "http://localhost:8080"


def test_server_config_validation_empty_url():
    """Test server configuration validation with empty URL."""
    config_data = {
        "fessBaseUrl": "",
        "domain": {
            "id": "test",
            "name": "Test",
            "labelFilter": "test",
        },
    }
    with pytest.raises(ValueError, match="fessBaseUrl cannot be empty"):
        ServerConfig(**config_data)


def test_load_config_missing_file(tmp_path, monkeypatch):
    """Test load_config with missing file."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_config()


def test_load_config_invalid_json(tmp_path, monkeypatch):
    """Test load_config with invalid JSON."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_dir = tmp_path / ".mcp-feiss"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text("invalid json {")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config()


def test_load_config_valid(tmp_path, monkeypatch):
    """Test load_config with valid configuration."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    config_dir = tmp_path / ".mcp-feiss"
    config_dir.mkdir()
    config_file = config_dir / "config.json"

    config_data = {
        "fessBaseUrl": "http://localhost:8080",
        "domain": {
            "id": "test",
            "name": "Test Domain",
            "description": "Test",
            "labelFilter": "test",
        },
    }
    config_file.write_text(json.dumps(config_data))

    config = load_config()
    assert config.fessBaseUrl == "http://localhost:8080"
    assert config.domain.id == "test"
    assert config.domain.name == "Test Domain"
