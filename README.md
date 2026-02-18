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

### Quick Install (Recommended)

The easiest way to install MCP-Fess is using the automated installer:

```bash
git clone https://github.com/Buttje/mcp-fess.git
cd mcp-fess
python3 install.py
```

This will:
- Detect your operating system (Windows 10/11, Linux Ubuntu/Red Hat/Fedora)
- Create a virtual environment (`./venv`)
- Install all required dependencies
- Create an OS-specific launcher script (`start-mcp-fess.sh` or `start-mcp-fess.bat`)
- Generate an initial configuration file at `~/.mcp-feiss/config.json`

After installation, you can run the server directly:

**On Linux/macOS:**
```bash
./start-mcp-fess.sh
```

**On Windows:**
```cmd
start-mcp-fess.bat
```

#### Installer Options

```bash
# Custom virtual environment location
python3 install.py --venv-dir /path/to/venv

# Custom configuration directory
python3 install.py --config-dir /path/to/config

# Skip creating initial configuration
python3 install.py --no-config

# Show help
python3 install.py --help
```

### Manual Installation (From Source)

If you prefer manual installation:

```bash
git clone https://github.com/Buttje/mcp-fess.git
cd mcp-fess
pip install -e .
```

### Requirements

- Python 3.10 or higher
- A running Fess server instance

## Configuration
Create a configuration file at `~/.mcp-fess/config.json`.
### Minimal Configuration

The simplest configuration requires only the Fess server URL:

```json
{
  "fessBaseUrl": "http://localhost:8080"
}
```

This uses default values for all optional fields including a default domain with `id="default"` and `name="Default Domain"`.

### Full Configuration Example

For production use, you should provide explicit domain information and configure other settings:

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
    "maxChunkBytes": 1048576,
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
- **domain** (optional): Domain configuration with id, name, and optional description
  - Defaults to `{"id": "default", "name": "Default Domain"}` if not specified
  - Recommended to provide meaningful values for better tool identification
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
  - `maxPageSize`: Maximum number of search results per page (default 100)
  - `maxChunkBytes`: Maximum bytes returned by read_doc_content and fetch_content_chunk (default 1048576 = 1 MiB)
  - `maxInFlightRequests`: Maximum concurrent requests (default 32)
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
Debug logs are written to `~/.mcp-fess/log/<timestamp>_server.log` with elapsed time prefixes.

### HTTP Transport

```bash
mcp-fess --transport http
```

### Cody Mode (MCP 2024-11-05)

```bash
mcp-fess --cody
```

## Configuration

Create a configuration file at `~/.mcp-fess/config.json`.

## Agent Workflow

MCP-Fess provides a structured workflow for agents to efficiently search and retrieve information from Fess:

### Efficient Search Strategy

1. **(Optional) Discover labels**: Call `list_labels` to pick a label scope if you need to restrict the search space
2. **Search for documents**: Call `search` to get relevant hits and collect `doc_id`s
3. **Fetch content**: Call `fetch_content_chunk` (preferred) or `fetch_content_by_id` to read extracted UTF-8 text evidence from the index
4. **Refine**: Use evidence to refine the query; optionally use `suggest` and `popular_words` to expand/pivot

### Content Retrieval

- **Search results** contain only short summary/snippet fields
- **Full document text** is retrieved from the Fess index (not from origin URLs)
- **Text source priority**: `content` field → `body` field → `digest` field
- **Chunking**: For documents exceeding the maximum chunk size, use `fetch_content_chunk` to iterate through content:
  - Start with `offset=0`
  - If `hasMore=true`, set `offset = offset + returned_length` and call again
  - Repeat until `hasMore=false`

### Performance Tips

- Use `include_fields` parameter in search to limit payload to needed fields
- Use chunking for large documents instead of fetching entire content at once
- Leverage labels to scope searches and reduce result sets

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
Get query suggestions based on the index vocabulary. Use after reviewing evidence to generate grounded query expansions (synonyms, prefixes, near-terms).

**Parameters:**
- `prefix` (required): Search prefix
- `num` (optional): Number of suggestions (default 10)
- `fields` (optional): Fields to search in
- `lang` (optional): Language

### 4. Popular Words Tool
Get popular words/terms from the index. Use to discover dominant vocabulary for pivots, filters, and follow-up query formulation.

**Parameters:**
- `seed` (optional): Random seed
- `field` (optional): Field name

### 5. Health Tool
Check Fess server health status.

### 6. Job Progress Tool
Query status of long-running operations.

**Parameters:**
- `jobId` (required): Job identifier

### 7. Fetch Content Chunk Tool
Fetch a window of extracted UTF-8 text for a document from the Fess index (no origin URL fetch).

Use this after `search` when you need substantial evidence (sections/chapters/whole documents).

**Text source:** Index fields only (priority: `content` → `body` → `digest`). No origin URL fetch.

**Parameters:**
- `doc_id` (required): Document ID obtained from search results
- `offset` (optional): Character offset into document (default 0)
- `length` (optional): Number of characters to return (default maxChunkBytes)

**Returns:**
JSON with:
- `content`: The requested text chunk
- `hasMore`: Boolean indicating if more content exists beyond this chunk
- `offset`: The starting position of this chunk
- `length`: Actual length of returned content
- `totalLength`: Total document length in characters

**Example:**
```json
{
  "content": "Document content...",
  "hasMore": true,
  "offset": 0,
  "length": 1048576,
  "totalLength": 2500000
}
```

To retrieve the next chunk, use `offset: 1048576` with the same `length`.

### 8. Fetch Content By ID Tool
Fetch extracted UTF-8 text for a document from the Fess index in one call (no origin URL fetch).

Use when the document is expected to fit within the server's maximum chunk limit or when you want a quick read without managing offsets. If the document exceeds the limit, content is truncated; use `fetch_content_chunk` for full traversal.

**Text source:** Index fields only (priority: `content` → `body` → `digest`). No origin URL fetch.

**Parameters:**
- `doc_id` (required): Document ID obtained from search results

**Returns:**
JSON with:
- `content`: The document content (up to maximum chunk size)
- `totalLength`: Total document length in characters
- `truncated`: Boolean indicating if content was truncated due to size limits

## MCP Resources

Documents and labels are exposed as resources with URIs:
- `fess://<domain_id>/doc/<doc_id>` - Document metadata. Use `doc/{doc_id}/content` or the content fetch tools to retrieve extracted text.
- `fess://<domain_id>/doc/<doc_id>/content` - Document extracted text (index-only). Returns up to the server's maximum chunk limit. For longer documents, use `fetch_content_chunk` to iterate through the full extracted text.
- `fess://<domain_id>/labels` - Available labels catalog with descriptions.

## Best Practices for Agents

When using MCP-Fess with LLM agents:

1. **Label Discovery**: Call `list_labels` at the start of a session or when switching domains to understand available search spaces
2. **Prefer Specific Labels**: Use specific labels (e.g., `"hr"`, `"engineering"`) over `"all"` when the user intent is clear, for more focused results
3. **Search First**: Always search for factual information rather than guessing or relying on general knowledge
4. **Progressive Refinement**: Start with broader searches (`label="all"`) and refine with specific labels based on initial results
5. **Large Documents**: Use the `fetch_content_chunk` tool to retrieve additional content when documents exceed maxChunkBytes (default 1 MiB)

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
