#!/usr/bin/env python3
"""
Installer script for mcp-fess server.

This script:
- Detects the operating system
- Creates a virtual environment
- Installs all required dependencies
- Installs the mcp-fess server
- Creates OS-specific launcher scripts
- Generates an initial configuration file
"""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path


# Colors for terminal output
class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_info(message: str) -> None:
    """Print info message."""
    print(f"{Colors.OKBLUE}[INFO]{Colors.ENDC} {message}")

def print_success(message: str) -> None:
    """Print success message."""
    print(f"{Colors.OKGREEN}[SUCCESS]{Colors.ENDC} {message}")

def print_error(message: str) -> None:
    """Print error message."""
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {message}")

def print_warning(message: str) -> None:
    """Print warning message."""
    print(f"{Colors.WARNING}[WARNING]{Colors.ENDC} {message}")

def print_header(message: str) -> None:
    """Print header message."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{message}{Colors.ENDC}\n")

def detect_os() -> tuple[str, str]:
    """
    Detect the operating system.

    Returns:
        tuple: (os_type, os_name) where os_type is 'windows' or 'linux',
               and os_name is more specific version info
    """
    system = platform.system().lower()

    if system == "windows":
        # Try to detect Windows version
        platform.version()
        release = platform.release()

        if release == "10":
            return ("windows", "Windows 10")
        elif release == "11":
            return ("windows", "Windows 11")
        else:
            return ("windows", f"Windows {release}")

    elif system == "linux":
        # Try to detect Linux distribution
        try:
            with Path("/etc/os-release").open() as f:
                os_release = f.read()

            if "ubuntu" in os_release.lower():
                return ("linux", "Ubuntu")
            elif "red hat" in os_release.lower() or "rhel" in os_release.lower():
                return ("linux", "Red Hat")
            elif "fedora" in os_release.lower():
                return ("linux", "Fedora")
            else:
                return ("linux", "Linux (Unknown Distribution)")
        except FileNotFoundError:
            return ("linux", "Linux (Unknown Distribution)")

    elif system == "darwin":
        return ("macos", "macOS")

    else:
        return ("unknown", f"Unknown ({system})")

def check_python_version() -> bool:
    """
    Check if Python version meets requirements (>=3.10).

    Returns:
        bool: True if version is sufficient
    """
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print_error(f"Python 3.10 or higher is required. Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    return True

def create_venv(venv_path: Path) -> bool:
    """
    Create a virtual environment.

    Args:
        venv_path: Path where the venv should be created

    Returns:
        bool: True if successful
    """
    try:
        print_info(f"Creating virtual environment at {venv_path}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        print_success(f"Virtual environment created at {venv_path}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        return False

def get_venv_python(venv_path: Path, os_type: str) -> Path:
    """
    Get the path to Python executable in the venv.

    Args:
        venv_path: Path to the virtual environment
        os_type: Operating system type ('windows' or 'linux')

    Returns:
        Path to Python executable
    """
    if os_type == "windows":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"

def get_venv_pip(venv_path: Path, os_type: str) -> Path:
    """
    Get the path to pip executable in the venv.

    Args:
        venv_path: Path to the virtual environment
        os_type: Operating system type ('windows' or 'linux')

    Returns:
        Path to pip executable
    """
    if os_type == "windows":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"

def upgrade_pip(venv_path: Path, os_type: str) -> bool:
    """
    Upgrade pip in the virtual environment.

    Args:
        venv_path: Path to the virtual environment
        os_type: Operating system type

    Returns:
        bool: True if successful
    """
    try:
        python_exe = get_venv_python(venv_path, os_type)
        print_info("Upgrading pip...")
        subprocess.run(
            [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
            capture_output=True
        )
        print_success("pip upgraded successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_warning(f"Failed to upgrade pip: {e}")
        return False

def install_dependencies(venv_path: Path, os_type: str, project_root: Path) -> bool:
    """
    Install project dependencies in the virtual environment.

    Args:
        venv_path: Path to the virtual environment
        os_type: Operating system type
        project_root: Root directory of the project

    Returns:
        bool: True if successful
    """
    try:
        pip_exe = get_venv_pip(venv_path, os_type)
        print_info("Installing mcp-fess and dependencies...")

        # Install in editable mode with the project
        subprocess.run(
            [str(pip_exe), "install", "-e", str(project_root)],
            check=True
        )

        print_success("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def create_launcher_windows(venv_path: Path, install_dir: Path) -> bool:
    """
    Create Windows launcher script (.bat file).

    Args:
        venv_path: Path to the virtual environment
        install_dir: Installation directory

    Returns:
        bool: True if successful
    """
    try:
        launcher_path = install_dir / "start-mcp-fess.bat"
        python_exe = venv_path / "Scripts" / "python.exe"

        launcher_content = f"""@echo off
REM MCP-Fess Server Launcher for Windows
REM This script starts the MCP-Fess server without requiring manual venv activation

"{python_exe}" -m mcp_fess %*
"""

        with launcher_path.open("w") as f:
            f.write(launcher_content)

        print_success(f"Windows launcher created: {launcher_path}")
        print_info(f"You can now run the server with: {launcher_path}")
        return True
    except Exception as e:
        print_error(f"Failed to create Windows launcher: {e}")
        return False

def create_launcher_unix(venv_path: Path, install_dir: Path) -> bool:
    """
    Create Unix/Linux launcher script.

    Args:
        venv_path: Path to the virtual environment
        install_dir: Installation directory

    Returns:
        bool: True if successful
    """
    try:
        launcher_path = install_dir / "start-mcp-fess.sh"
        python_exe = venv_path / "bin" / "python"

        launcher_content = f"""#!/bin/bash
# MCP-Fess Server Launcher for Linux/Unix
# This script starts the MCP-Fess server without requiring manual venv activation

"{python_exe}" -m mcp_fess "$@"
"""

        with launcher_path.open("w") as f:
            f.write(launcher_content)

        # Make the script executable
        launcher_path.chmod(0o755)

        print_success(f"Unix launcher created: {launcher_path}")
        print_info(f"You can now run the server with: ./{launcher_path}")
        return True
    except Exception as e:
        print_error(f"Failed to create Unix launcher: {e}")
        return False

def create_initial_config(config_dir: Path | None = None) -> bool:
    """
    Create initial configuration file.

    Args:
        config_dir: Optional custom config directory. If None, uses default ~/.mcp-feiss/

    Returns:
        bool: True if successful
    """
    try:
        if config_dir is None:
            config_dir = Path.home() / ".mcp-feiss"

        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.json"

        # Check if config already exists
        if config_path.exists():
            print_warning(f"Configuration file already exists at {config_path}")
            response = input("Do you want to overwrite it? [y/N]: ").strip().lower()
            if response != 'y':
                print_info("Keeping existing configuration file")
                return True

        # Create minimal initial configuration
        initial_config = {
            "fessBaseUrl": "http://localhost:8080",
            "domain": {
                "id": "default",
                "name": "Default Domain",
                "description": "Default domain for MCP-Fess server"
            },
            "labels": {
                "all": {
                    "title": "All documents",
                    "description": "Search across the whole Fess index without label filtering.",
                    "examples": ["company policy", "architecture decision record"]
                }
            },
            "defaultLabel": "all",
            "strictLabels": True,
            "logging": {
                "level": "info",
                "retainDays": 7
            }
        }

        with config_path.open("w") as f:
            json.dump(initial_config, f, indent=2)

        print_success(f"Initial configuration created at {config_path}")
        print_info("Please edit this file to configure your Fess server URL and other settings")
        return True
    except Exception as e:
        print_error(f"Failed to create initial configuration: {e}")
        return False

def main() -> int:
    """Main installation function."""
    parser = argparse.ArgumentParser(
        description="Install MCP-Fess server with virtual environment"
    )
    parser.add_argument(
        "--venv-dir",
        type=Path,
        default=None,
        help="Custom directory for virtual environment (default: ./venv)"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Custom directory for configuration (default: ~/.mcp-feiss/)"
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Skip creating initial configuration file"
    )

    args = parser.parse_args()

    # Print header
    print_header("MCP-Fess Server Installer")

    # Detect OS
    os_type, os_name = detect_os()
    print_info(f"Detected operating system: {os_name}")

    if os_type == "unknown":
        print_error("Unsupported operating system")
        return 1

    # Check Python version
    if not check_python_version():
        return 1

    print_success(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # Determine installation paths
    project_root = Path(__file__).parent.absolute()
    venv_path = args.venv_dir if args.venv_dir else project_root / "venv"

    print_info(f"Project root: {project_root}")
    print_info(f"Virtual environment will be created at: {venv_path}")

    # Create virtual environment
    if not create_venv(venv_path):
        return 1

    # Upgrade pip
    upgrade_pip(venv_path, os_type)

    # Install dependencies
    if not install_dependencies(venv_path, os_type, project_root):
        return 1

    # Create launcher script
    print_header("Creating Launcher Script")
    if os_type == "windows":
        if not create_launcher_windows(venv_path, project_root):
            return 1
    else:
        if not create_launcher_unix(venv_path, project_root):
            return 1

    # Create initial configuration
    if not args.no_config:
        print_header("Creating Initial Configuration")
        create_initial_config(args.config_dir)

    # Print final instructions
    print_header("Installation Complete!")
    print_success("MCP-Fess server has been installed successfully")
    print()
    print("Next steps:")
    print("  1. Edit the configuration file at ~/.mcp-feiss/config.json")
    print("     (Update the fessBaseUrl to point to your Fess server)")
    print()
    if os_type == "windows":
        print(f"  2. Run the server: {project_root / 'start-mcp-fess.bat'}")
        print(f"     Or with debug: {project_root / 'start-mcp-fess.bat'} --debug")
    else:
        print(f"  2. Run the server: ./{project_root / 'start-mcp-fess.sh'}")
        print(f"     Or with debug: ./{project_root / 'start-mcp-fess.sh'} --debug")
    print()
    print("For more information, see README.md")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
