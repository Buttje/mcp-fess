"""CLI entrypoint for mcp-fess snippet generation."""

import argparse
import json
import logging
import sys
from pathlib import Path


def _resolve_snippets_root(config: object, output_folder: str, logger: logging.Logger) -> Path:
    """Resolve the snippets output directory from config and output_folder."""
    from mcp_fess.snippet_engine.compose_parser import find_host_fess_data_dir

    host_data_dir = find_host_fess_data_dir(
        config.fessComposePath,  # type: ignore[attr-defined]
        service_name=config.fessComposeService,  # type: ignore[attr-defined]
        container_mount=config.fessDataMount,  # type: ignore[attr-defined]
    )
    return host_data_dir / output_folder


def main() -> None:
    """Run snippet generation from the command line."""
    parser = argparse.ArgumentParser(
        prog="mcp-fess-snippets",
        description="Generate Markdown snippets from source documents for Fess indexing.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- add (default) subcommand ---
    add_parser = subparsers.add_parser(
        "add",
        help="Generate snippets for documents in a directory (skips already-processed files).",
    )
    add_parser.add_argument("--input", required=True, help="Input directory to scan")
    add_parser.add_argument(
        "--output-folder", required=True, help="Output folder name under host data mount"
    )
    add_parser.add_argument(
        "--include", nargs="*", default=None, help="Include glob patterns (e.g. '**/*.pdf')"
    )
    add_parser.add_argument("--exclude", nargs="*", default=None, help="Exclude glob patterns")
    add_parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # --- delete subcommand ---
    del_parser = subparsers.add_parser(
        "delete",
        help="Remove snippets and images for a specific document and update the manifest.",
    )
    del_parser.add_argument(
        "--file", required=True, help="Absolute path of the original source document to delete"
    )
    del_parser.add_argument(
        "--output-folder", required=True, help="Output folder name under host data mount"
    )
    del_parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # --- update subcommand ---
    upd_parser = subparsers.add_parser(
        "update",
        help="Re-generate snippets for a specific document (delete existing, then re-process).",
    )
    upd_parser.add_argument(
        "--file", required=True, help="Absolute path of the original source document to update"
    )
    upd_parser.add_argument(
        "--output-folder", required=True, help="Output folder name under host data mount"
    )
    upd_parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    # Support legacy invocation without a subcommand (treated as "add")
    parser.add_argument("--input", help=argparse.SUPPRESS)
    parser.add_argument("--output-folder", help=argparse.SUPPRESS)
    parser.add_argument("--include", nargs="*", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--exclude", nargs="*", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--verbose", "-v", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Determine effective command
    command = args.command or "add"

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

    # Resolve snippets_root
    try:
        snippets_root = _resolve_snippets_root(config, args.output_folder, logger)
    except Exception as e:
        logger.error("Failed to resolve host data directory: %s", e)
        sys.exit(1)

    manifest_path = snippets_root / "manifest.jsonl"

    # ------------------------------------------------------------------ delete
    if command == "delete":
        from mcp_fess.snippet_engine.manifest import remove_document_from_manifest

        file_path = Path(args.file).resolve()
        result = remove_document_from_manifest(manifest_path, file_path)
        if not result["found"]:
            logger.warning("Document not found in manifest: %s", file_path)
        else:
            logger.info(
                "Deleted %d snippet part(s) and %d image(s) for %s",
                result["removed_parts"],
                result["removed_images"],
                file_path,
            )
        print(json.dumps(result, indent=2))
        return

    # ------------------------------------------------------------------ update
    if command == "update":
        from mcp_fess.snippet_engine.convert import convert_document
        from mcp_fess.snippet_engine.image_store import compute_doc_hash
        from mcp_fess.snippet_engine.manifest import (
            append_manifest_entry,
            remove_document_from_manifest,
        )
        from mcp_fess.snippet_engine.md_writer import write_snippets

        file_path = Path(args.file).resolve()
        images_root = snippets_root / "images"
        snippets_root.mkdir(parents=True, exist_ok=True)
        images_root.mkdir(parents=True, exist_ok=True)

        # Step 1: delete existing artifacts
        remove_document_from_manifest(manifest_path, file_path)

        # Step 2: re-generate
        doc_hash = compute_doc_hash(file_path)
        warnings_list: list[str] = []
        try:
            page_lines, images = convert_document(file_path, images_root, doc_hash)
            parts = write_snippets(file_path, page_lines, snippets_root, doc_hash)
            append_manifest_entry(manifest_path, file_path, doc_hash, parts, images, warnings_list)
            logger.info(
                "Updated: %s -> %d parts, %d images", file_path.name, len(parts), len(images)
            )
            result = {"updated": True, "parts": len(parts), "images": len(images)}
        except Exception as e:
            warnings_list.append(str(e))
            logger.error("Failed to update %s: %s", file_path, e)
            append_manifest_entry(manifest_path, file_path, doc_hash, [], [], warnings_list)
            result = {"updated": False, "error": str(e)}

        print(json.dumps(result, indent=2))
        return

    # ------------------------------------------------------------------ add
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

    processed = 0
    skipped = 0
    failed = 0

    from mcp_fess.snippet_engine.convert import convert_document
    from mcp_fess.snippet_engine.image_store import compute_doc_hash
    from mcp_fess.snippet_engine.manifest import append_manifest_entry, is_document_in_manifest
    from mcp_fess.snippet_engine.md_writer import write_snippets

    for file_path in files:
        if is_document_in_manifest(manifest_path, file_path):
            logger.info("Skipping already-processed: %s", file_path.name)
            skipped += 1
            continue

        doc_hash = compute_doc_hash(file_path)
        warnings_list: list[str] = []
        try:
            page_lines, images = convert_document(file_path, images_root, doc_hash)
            parts = write_snippets(file_path, page_lines, snippets_root, doc_hash)
            append_manifest_entry(
                manifest_path, file_path, doc_hash, parts, images, warnings_list
            )
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
        "skipped": skipped,
        "failed": failed,
        "output_root": str(snippets_root),
        "manifest_path": str(manifest_path),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
