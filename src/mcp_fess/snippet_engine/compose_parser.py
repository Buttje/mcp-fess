"""Parse docker compose files to extract host directory mount paths."""

from pathlib import Path
from typing import Any

import yaml


def find_host_fess_data_dir(
    compose_path: str | Path,
    service_name: str | None = None,
    container_mount: str = "/data/fess",
) -> Path:
    """Find the host directory that maps to container_mount in the compose file.

    Args:
        compose_path: Path to the docker compose file.
        service_name: Name of the service to look in (optional; auto-detect if None).
        container_mount: Container-side mount path to match (default '/data/fess').

    Returns:
        Absolute Path of the host directory.

    Raises:
        FileNotFoundError: If compose_path does not exist.
        ValueError: If no matching volume mapping is found.
    """
    compose_path = Path(compose_path)
    if not compose_path.exists():
        raise FileNotFoundError(f"Compose file not found: {compose_path}")

    with compose_path.open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    services: dict[str, Any] = data.get("services", {})
    if not services:
        raise ValueError(f"No services found in compose file: {compose_path}")

    def _parse_volume(volume: str) -> tuple[str, str]:
        """Return (host_path, container_path) from a short-form volume string."""
        parts = volume.split(":")
        if len(parts) < 2:
            return volume, volume
        # Handle Windows drive letters: C:\path:/container/path[:mode]
        if len(parts[0]) == 1 and parts[0].isalpha() and len(parts) >= 3:
            host_path = parts[0] + ":" + parts[1]
            container_path = parts[2]
            return host_path, container_path
        # parts[2] may be mode e.g. 'rw' or 'ro' - ignore it
        return parts[0], parts[1]

    def _check_service(service_cfg: dict[str, Any]) -> str | None:
        volumes = service_cfg.get("volumes", [])
        for vol in volumes:
            if isinstance(vol, str):
                host_path, container_path = _parse_volume(vol)
                if container_path == container_mount:
                    return host_path
            elif isinstance(vol, dict):
                # Long form: {type, source, target}
                if vol.get("type") == "bind" and vol.get("target") == container_mount:
                    src = vol.get("source")
                    if src:
                        return str(src)
        return None

    if service_name:
        if service_name not in services:
            raise ValueError(f"Service '{service_name}' not found in compose file")
        host_path = _check_service(services[service_name])
        if host_path is None:
            raise ValueError(
                f"No volume mapping to '{container_mount}' found in service '{service_name}'"
            )
        return Path(host_path)

    # Auto-detect: scan all services
    for _svc_name, svc_cfg in services.items():
        host_path = _check_service(svc_cfg)
        if host_path is not None:
            return Path(host_path)

    raise ValueError(
        f"No volume mapping to '{container_mount}' found in any service in: {compose_path}"
    )
