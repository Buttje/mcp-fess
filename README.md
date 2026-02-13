# mcp-fess

An MCP (Model Context Protocol) Server implementation for Fess, providing seamless integration with the Fess search engine.

## Features

- Model Context Protocol server implementation
- Integration with Fess search engine
- Type-safe Python implementation
- Comprehensive test coverage

## Installation

### From PyPI (when published)

```bash
pip install mcp-fess
```

### From Source

```bash
git clone https://github.com/Buttje/mcp-fess.git
cd mcp-fess
pip install -e .
```

## Usage

```bash
# Run the MCP server
mcp-fess
```

Or programmatically:

```python
from mcp_fess.server import main

main()
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

### Quick Start

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src tests

# Run type checking
mypy src
```

## Requirements

- Python 3.10 or higher

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
