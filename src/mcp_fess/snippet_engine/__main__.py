"""CLI entrypoint for mcp-fess snippet generation."""

import argparse
import json
import logging
import sys
from pathlib import Path


def main() -> None:
    """Run snippet generation from the command line."""
    parser = argparse.ArgumentParser(
        prog="mcp-fess-snippets",
        description="Generate Markdown snippets from source documents for Fess indexing.",
    )
    parser.add_argument("--input", required=True, help="Input directory to scan")
    parser.add_argument(
        "--output-folder", required=True, help="Output folder name under host data mount"
    )
    parser.add_argument(
        "--include", nargs="*", default=None, help="Include glob patterns (e.g. '**/*.pdf')"
    )
    parser.add_argument("--exclude", nargs="*", default=None, help="Exclude glob patterns")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("mcp_fess.snippet_engine")

    # Load config
    try:
        from mcp_fess.config import load_config

        config = load_config()
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        sys.exit(1)

    if not config.fessComposePath:
        logger.error("fessComposePath is required in config for snippet generation")
        sys.exit(1)

    # Resolve snippets_root via compose parser
    try:
        from mcp_fess.snippet_engine.compose_parser import find_host_fess_data_dir

        host_data_dir = find_host_fess_data_dir(
            config.fessComposePath,
            service_name=config.fessComposeService,
            container_mount=config.fessDataMount,
        )
    except Exception as e:
        logger.error("Failed to resolve host data directory: %s", e)
        sys.exit(1)

    snippets_root = host_data_dir / args.output_folder
    images_root = snippets_root / "images"
    snippets_root.mkdir(parents=True, exist_ok=True)
    images_root.mkdir(parents=True, exist_ok=True)

    input_dir = Path(args.input).resolve()

    # Scan
    from mcp_fess.snippet_engine.scan import scan_directory

    try:
        files = scan_directory(input_dir, include_globs=args.include, exclude_globs=args.exclude)
    except Exception as e:
        logger.error("Scan failed: %s", e)
        sys.exit(1)

    logger.info("Found %d files to process", len(files))

    manifest_path = snippets_root / "manifest.jsonl"
    processed = 0
    failed = 0

    from mcp_fess.snippet_engine.convert import convert_document
    from mcp_fess.snippet_engine.image_store import compute_doc_hash
    from mcp_fess.snippet_engine.manifest import append_manifest_entry
    from mcp_fess.snippet_engine.md_writer import write_snippets

    for file_path in files:
        doc_hash = compute_doc_hash(file_path)
        warnings_list: list[str] = []
        try:
            page_lines, images = convert_document(file_path, images_root, doc_hash)
            parts = write_snippets(file_path, page_lines, snippets_root, doc_hash)
            append_manifest_entry(manifest_path, file_path, doc_hash, parts, images, warnings_list)
            processed += 1
            logger.info(
                "Processed: %s -> %d parts, %d images", file_path.name, len(parts), len(images)
            )
        except Exception as e:
            warnings_list.append(str(e))
            logger.error("Failed to process %s: %s", file_path, e)
            append_manifest_entry(manifest_path, file_path, doc_hash, [], [], warnings_list)
            failed += 1

    summary = {
        "processed": processed,
        "failed": failed,
        "output_root": str(snippets_root),
        "manifest_path": str(manifest_path),
    }
    print(json.dumps(summary, indent=2))
    logger.info("Done. Processed: %d, Failed: %d", processed, failed)
    logger.info("Output root: %s", snippets_root)
    logger.info("Manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
