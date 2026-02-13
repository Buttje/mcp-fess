# mcp-fess

An MCP (Model Context Protocol) bridge server for Fess search engine, enabling Large Language Models (LLMs) to query and retrieve domain-specific information through structured tools and resources.

## Features

- **MCP Protocol Support**: Implements MCP specification versions 2025-03-26 (default) and 2024-11-05 (--cody mode)
- **Full Fess API Integration**: Search, suggest, popular words, labels, and health check endpoints
- **Resource Management**: Expose Fess documents as MCP resources with content fetching
- **Domain Filtering**: Automatic filtering by Fess labels for knowledge domain isolation
- **Multiple Transports**: stdio (default) and HTTP transport modes
- **Content Extraction**: Fetch and convert HTML and PDF documents to plain text
- **Security**: Configurable authentication, host allowlists, and private network protection
- **Logging**: Comprehensive logging with debug mode support

## Installation

### From Source

```bash
git clone https://github.com/Buttje/mcp-fess.git
cd mcp-fess
pip install -e .
```

### Requirements

- Python 3.10 or higher
- A running Fess server instance

## Configuration

Create a configuration file at `~/.mcp-feiss/config.json`:

```json
{
  "fessBaseUrl": "http://localhost:8080",
  "domain": {
    "id": "my_domain",
    "name": "My Knowledge Domain",
    "description": "Description of the knowledge domain",
    "labelFilter": "my_label"
  },
  "httpTransport": {
    "bindAddress": "127.0.0.1",
    "port": 3000,
    "path": "/mcp",
    "enableSse": true
  },
  "timeouts": {
    "fessRequestTimeoutMs": 30000,
    "longRunningThresholdMs": 2000
  },
  "limits": {
    "maxPageSize": 100,
    "maxChunkBytes": 262144,
    "maxInFlightRequests": 32
  },
  "logging": {
    "level": "info",
    "retainDays": 7
  },
  "security": {
    "httpAuthToken": null,
    "allowNonLocalhostBind": false
  },
  "contentFetch": {
    "enabled": true,
    "maxBytes": 5242880,
    "timeoutMs": 20000,
    "allowedSchemes": ["http", "https"],
    "allowPrivateNetworkTargets": false,
    "allowedHostAllowlist": null,
    "userAgent": "MCP-Fess/1.0",
    "enablePdf": false
  }
}
```

### Configuration Fields

- **fessBaseUrl** (required): Base URL of your Fess server
- **domain** (required): Domain configuration with id, name, description, and labelFilter
- **httpTransport**: HTTP transport settings (for HTTP mode)
- **timeouts**: Request timeout configurations
- **limits**: Resource limits for requests and responses
- **logging**: Logging level and retention settings
- **security**: Authentication and network security settings
- **contentFetch**: Document content fetching configuration

## Usage

### Basic Usage (stdio transport)

```bash
mcp-fess
```

### Using FastMCP CLI

You can also run the server using the `fastmcp` CLI tool:

```bash
fastmcp run src/mcp_fess/app.py
```

Or use the package directly:

```bash
python -m mcp_fess
```

### With Debug Logging

```bash
mcp-fess --debug
```

Debug logs are written to `~/.mcp-feiss/log/<timestamp>_server.log` with elapsed time prefixes.

### HTTP Transport

```bash
mcp-fess --transport http
```

### Cody Mode (MCP 2024-11-05)

```bash
mcp-fess --cody
```

## MCP Tools

The server exposes the following tools (prefixed with `fess_<domain_id>_`):

### 1. Search Tool
Search documents in the knowledge domain.

**Parameters:**
- `query` (required): Search term
- `pageSize` (optional): Number of results (default 20, max 100)
- `start` (optional): Starting index (default 0)
- `sort` (optional): Sort order
- `lang` (optional): Search language
- `includeFields` (optional): Fields to include in results

### 2. Suggest Tool
Get search term suggestions.

**Parameters:**
- `prefix` (required): Search prefix
- `num` (optional): Number of suggestions (default 10)
- `fields` (optional): Fields to search in
- `lang` (optional): Language

### 3. Popular Words Tool
Retrieve popular/trending words.

**Parameters:**
- `seed` (optional): Random seed
- `field` (optional): Field name

### 4. List Labels Tool
List all labels configured in Fess.

### 5. Health Tool
Check Fess server health status.

### 6. Job Progress Tool
Query status of long-running operations.

**Parameters:**
- `jobId` (required): Job identifier

## MCP Resources

Documents are exposed as resources with URIs:
- `fess://<domain_id>/doc/<doc_id>` - Document metadata
- `fess://<domain_id>/doc/<doc_id>/content` - Full document content

Resources include the Knowledge Domain block in descriptions, enabling LLMs to understand the domain context.

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

# Format code
ruff format src tests
```

## Architecture

The server consists of:
- **Configuration Module** (`config.py`): Loads and validates configuration
- **Fess Client** (`fess_client.py`): HTTP client for Fess REST API
- **Server** (`server.py`): MCP server implementation with tools and resources
- **Logging** (`logging_utils.py`): Logging utilities with elapsed time support

## Security Considerations

- Default binding is loopback only (127.0.0.1)
- HTTP authentication via bearer tokens (optional)
- Private network target blocking (configurable)
- Host allowlists for content fetching
- Scheme restrictions for content fetching

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## References

- [Fess API Documentation](https://fess.codelibs.org/15.4/api/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
