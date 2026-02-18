"""Configuration management for MCP-Fess server."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("mcp_fess")


class LabelDescriptor(BaseModel):
    """Configuration for a single label."""

    title: str
    description: str
    examples: list[str] = Field(default_factory=list)


class DomainConfig(BaseModel):
    """Domain configuration."""

    id: str
    name: str
    description: str | None = None
    labelFilter: str | None = Field(default=None, alias="labelFilter")


class HttpTransportConfig(BaseModel):
    """HTTP transport configuration."""

    bindAddress: str = "127.0.0.1"
    port: int = 0
    path: str = "/mcp"
    enableSse: bool = True


class TimeoutsConfig(BaseModel):
    """Timeout configuration."""

    fessRequestTimeoutMs: int = 30000
    longRunningThresholdMs: int = 2000


class LimitsConfig(BaseModel):
    """Limits configuration."""

    maxPageSize: int = 100
    maxChunkBytes: int = 1048576  # 1 MiB - allows agents to retrieve larger sections
    maxInFlightRequests: int = 32


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "info"
    retainDays: int = 7


class SecurityConfig(BaseModel):
    """Security configuration."""

    httpAuthToken: str | None = None
    allowNonLocalhostBind: bool = False


class ContentFetchConfig(BaseModel):
    """Content fetch configuration."""

    enabled: bool = True
    maxBytes: int = 5 * 1024 * 1024
    timeoutMs: int = 20000
    allowedSchemes: list[str] = Field(default_factory=lambda: ["http", "https"])
    allowPrivateNetworkTargets: bool = False
    allowedHostAllowlist: list[str] | None = None
    userAgent: str = "MCP-Fess/1.0"
    enablePdf: bool = False


class ServerConfig(BaseModel):
    """Main server configuration."""

    fessBaseUrl: str
    domain: DomainConfig = Field(
        default_factory=lambda: DomainConfig(
            id="default", name="Default Domain", description=None
        )
    )
    labels: dict[str, LabelDescriptor] = Field(default_factory=dict)
    defaultLabel: str = "all"
    strictLabels: bool = True
    httpTransport: HttpTransportConfig = Field(default_factory=HttpTransportConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    contentFetch: ContentFetchConfig = Field(default_factory=ContentFetchConfig)

    @field_validator("fessBaseUrl")
    @classmethod
    def validate_fess_url(cls, v: str) -> str:
        """Validate Fess base URL."""
        if not v:
            raise ValueError("fessBaseUrl cannot be empty")
        return v.rstrip("/")

    def get_effective_default_label(self) -> str:
        """Get the effective default label, handling backward compatibility."""
        # Backward compatibility: use domain.labelFilter if present and defaultLabel is default value
        if self.domain.labelFilter and self.defaultLabel == "all":
            logger.warning(
                "domain.labelFilter is deprecated. Please use defaultLabel instead. "
                "Setting defaultLabel to '%s'",
                self.domain.labelFilter,
            )
            return self.domain.labelFilter

        return self.defaultLabel

    model_config = {"populate_by_name": True}


def load_config() -> ServerConfig:
    """Load configuration from ~/.mcp-fess/config.json."""
    config_dir = Path.home() / ".mcp-fess"
    config_path = config_dir / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create {config_path} with required configuration."
        )

    try:
        with config_path.open(encoding="utf-8") as f:
            config_data: dict[str, Any] = json.load(f)
        return ServerConfig(**config_data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to load configuration: {e}") from e


def ensure_log_directory() -> Path:
    """Ensure log directory exists and return its path."""
    log_dir = Path.home() / ".mcp-fess" / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir