# mcp-fess

An MCP (Model Context Protocol) bridge server for Fess search engine, enabling Large Language Models (LLMs) to query and retrieve domain-specific information through structured tools and resources.

## Features

- **MCP Protocol Support**: Implements MCP specification versions 2025-03-26 (default) and 2024-11-05 (--cody mode)
- **Full Fess API Integration**: Search, suggest, popular words, labels, and health check endpoints
- **Resource Management**: Expose Fess documents as MCP resources with content fetching
- **Label-based Filtering**: Flexible label-based search with configurable descriptions and examples
- **Label Discovery**: Automatic discovery of labels from Fess with intelligent caching
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
    "description": "Description of the knowledge domain"
  },
  "labels": {
    "all": {
      "title": "All documents",
      "description": "Search across the whole Fess index without label filtering.",
      "examples": ["company policy", "architecture decision record"]
    },
    "hr": {
      "title": "HR policies",
      "description": "Employee handbook, benefits, leave, HR forms.",
      "examples": ["vacation policy", "parental leave"]
    },
    "engineering": {
      "title": "Engineering documentation",
      "description": "Technical documentation, API references, architecture guides.",
      "examples": ["API documentation", "deployment guide"]
    }
  },
  "defaultLabel": "all",
  "strictLabels": true,
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
- **domain** (required): Domain configuration with id, name, and optional description
- **labels** (optional): Label definitions with descriptions and examples
  - Each label has a `title`, `description`, and `examples` array
  - The `"all"` label is always available (even if not explicitly configured) and means "no label filtering"
  - Label descriptions are stored in MCP config, not in Fess
- **defaultLabel** (optional, default: "all"): Default label to use when none is specified in search
- **strictLabels** (optional, default: true): 
  - `true`: Only allow labels defined in config or present in Fess
  - `false`: Allow any label value (with warning for undefined labels)
- **httpTransport**: HTTP transport settings (for HTTP mode)
- **timeouts**: Request timeout configurations
- **limits**: Resource limits for requests and responses
- **logging**: Logging level and retention settings
- **security**: Authentication and network security settings
- **contentFetch**: Document content fetching configuration

### Backward Compatibility

For backward compatibility with older configurations, `domain.labelFilter` is still supported but deprecated:

```json
{
  "domain": {
    "id": "my_domain",
    "name": "My Knowledge Domain",
    "labelFilter": "my_label"
  }
}
```

When `domain.labelFilter` is present and `defaultLabel` is not explicitly set, the server will use `labelFilter` as the default label and log a deprecation warning. We recommend migrating to the new configuration format:

```json
{
  "domain": {
    "id": "my_domain",
    "name": "My Knowledge Domain"
  },
  "defaultLabel": "my_label",
  "labels": {
    "my_label": {
      "title": "My Label",
      "description": "Documents with my_label",
      "examples": []
    }
  }
}
```

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
Search documents in Fess. **Use this tool whenever you need factual internal information; don't guess—search first.**

**Parameters:**
- `query` (required): Search term
- `label` (optional): Label value to scope the search
  - Use `"all"` (default) to search across the entire index without label filtering
  - Use a specific label value (e.g., `"hr"`, `"engineering"`) to search within that label
  - Call `list_labels` to see available labels and their descriptions
- `pageSize` (optional): Number of results (default 20, max 100)
- `start` (optional): Starting index (default 0)
- `sort` (optional): Sort order
- `lang` (optional): Search language
- `includeFields` (optional): Fields to include in results

**Label behavior:**
- When `label="all"`: No label filter is applied (searches entire Fess index)
- When `label=<value>`: Applies `fields.label=[<value>]` filter to Fess query
- When label is omitted: Uses the configured `defaultLabel`

### 2. List Labels Tool
List available Fess labels and what each label contains. **Call this if unsure which label to use.**

Returns a catalog of labels with:
- Label values and names
- Descriptions and usage examples (from MCP config)
- Availability status (present in Fess or config-only)
- Default label setting
- Strict mode status

### 3. Suggest Tool
Get search term suggestions.

**Parameters:**
- `prefix` (required): Search prefix
- `num` (optional): Number of suggestions (default 10)
- `fields` (optional): Fields to search in
- `lang` (optional): Language

### 4. Popular Words Tool
Retrieve popular/trending words.

**Parameters:**
- `seed` (optional): Random seed
- `field` (optional): Field name

### 5. Health Tool
Check Fess server health status.

### 6. Job Progress Tool
Query status of long-running operations.

**Parameters:**
- `jobId` (required): Job identifier

## MCP Resources

Documents and labels are exposed as resources with URIs:
- `fess://<domain_id>/doc/<doc_id>` - Document metadata
- `fess://<domain_id>/doc/<doc_id>/content` - Full document content
- `fess://<domain_id>/labels` - Available labels catalog

Resources include the Knowledge Domain block in descriptions, enabling LLMs to understand the domain context.

## Best Practices for Agents

When using MCP-Fess with LLM agents:

1. **Label Discovery**: Call `list_labels` at the start of a session or when switching domains to understand available search spaces
2. **Prefer Specific Labels**: Use specific labels (e.g., `"hr"`, `"engineering"`) over `"all"` when the user intent is clear, for more focused results
3. **Search First**: Always search for factual information rather than guessing or relying on general knowledge
4. **Progressive Refinement**: Start with broader searches (`label="all"`) and refine with specific labels based on initial results

## Label Configuration Guide

Labels in MCP-Fess serve as search spaces to help agents find the right information:

### Label Descriptions
- **Stored in MCP config**, not in Fess (Fess labels API only provides label values and names)
- Include meaningful descriptions to guide agent behavior
- Provide examples of typical queries for each label

### Label Discovery
- Labels are automatically discovered from Fess via `/api/v1/labels` API
- Cached for 5 minutes to reduce load on Fess
- Config-defined labels are merged with live Fess labels

### Strict Mode
- **strict=true** (default): Only allows labels defined in config or present in Fess
- **strict=false**: Allows any label value, useful during development or when label structure is dynamic

### Example Configuration

```json
{
  "labels": {
    "all": {
      "title": "All documents",
      "description": "Search across the whole Fess index without label filtering.",
      "examples": ["company policy", "org chart"]
    },
    "hr": {
      "title": "HR policies",
      "description": "Employee handbook, benefits, leave policies, HR forms, and onboarding guides.",
      "examples": ["vacation policy", "parental leave", "401k enrollment"]
    },
    "engineering": {
      "title": "Engineering documentation",
      "description": "Technical docs, API references, architecture guides, deployment procedures.",
      "examples": ["API authentication", "deployment checklist", "system architecture"]
    },
    "product": {
      "title": "Product documentation",
      "description": "Product specs, roadmaps, feature docs, user guides.",
      "examples": ["feature requirements", "product roadmap Q1"]
    }
  },
  "defaultLabel": "all",
  "strictLabels": true
}
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
