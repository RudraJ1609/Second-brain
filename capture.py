"""
Phase 1 — The Archivist: one-command capture into raw/.

Usage:
  python capture.py "free text idea"
  python capture.py --url https://example.com/article
  python capture.py --file ./notes.pdf
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import socket
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import frontmatter
import requests
from pypdf import PdfReader
from pypdf.errors import PdfReadError

import config

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".py", ".rst"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
URL_FETCH_TIMEOUT = 8
URL_FETCH_MAX_BYTES = 512_000


class CaptureError(ValueError):
    """Raised for user-facing capture failures (no file written)."""


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _truncate(text: str, limit: int | None = None) -> tuple[str, bool]:
    limit = limit if limit is not None else config.MAX_CAPTURE_CHARS
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _is_private_host(hostname: str) -> bool:
    """Block obvious SSRF targets (EC-SEC-06)."""
    if not hostname:
        return True
    host = hostname.strip("[]").lower()
    if host in {"localhost", "metadata.google.internal"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return True
    return False


def _validate_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CaptureError(
            f"Invalid URL (need http/https with host): {url!r}"
        )
    if _is_private_host(parsed.hostname or ""):
        raise CaptureError(
            f"Refusing to fetch private/local host: {parsed.hostname}"
        )
    return url.strip()


def _fetch_url_title(url: str) -> tuple[str | None, str | None]:
    """
    Best-effort title fetch. Capture must succeed even if this fails (EC-CAP-13).
    Returns (title, warning).
    """
    try:
        with requests.get(
            url,
            timeout=URL_FETCH_TIMEOUT,
            stream=True,
            headers={"User-Agent": "SecondSelf-Capture/1.0"},
            allow_redirects=True,
        ) as resp:
            # Re-check final host after redirects
            final_host = urlparse(resp.url).hostname or ""
            if _is_private_host(final_host):
                return None, f"Blocked redirect to private host: {final_host}"

            if resp.status_code >= 400:
                return None, f"HTTP {resp.status_code} fetching title"

            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                chunks.append(chunk)
                size += len(chunk)
                if size >= URL_FETCH_MAX_BYTES:
                    break
            text = b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
            match = TITLE_RE.search(text)
            if not match:
                return None, None
            title = re.sub(r"\s+", " ", match.group(1)).strip()
            return title or None, None
    except requests.RequestException as exc:
        return None, f"Title fetch failed: {exc}"


def _extract_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_pdf(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        reader = PdfReader(str(path))
    except PdfReadError as exc:
        raise CaptureError(f"Could not read PDF {path}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — surface corrupt/encrypted PDFs
        raise CaptureError(f"Could not open PDF {path}: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise CaptureError(
                f"Password-protected PDF (cannot extract): {path}"
            ) from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Page extract warning: {exc}")
    text = "\n".join(parts).strip()
    if not text:
        warnings.append(
            "PDF had no extractable text (scanned/image-only?). "
            "Saved metadata only."
        )
    return text, warnings


def _extract_file_content(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return _extract_text_file(path), []
    if suffix in SUPPORTED_PDF_EXTENSIONS:
        return _extract_pdf(path)
    raise CaptureError(
        f"Unsupported file type {suffix!r}. "
        f"Supported: {sorted(SUPPORTED_TEXT_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS)}"
    )


def _resolve_input_file(file_path: str | Path) -> Path:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise CaptureError(f"File does not exist: {path}")
    if path.is_dir():
        raise CaptureError(f"Path is a directory, not a file: {path}")
    # Soft path-traversal guard: prefer files under project or user-provided absolute paths
    # but never follow into missing paths (already checked).
    return path


def _write_capture(
    *,
    capture_id: str,
    capture_type: str,
    source: str | None,
    body: str,
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    config.ensure_directories()
    out_path = config.RAW_DIR / f"{capture_id}.md"
    if out_path.exists():
        # Extremely unlikely with UUID; never overwrite (EC-CAP-19)
        raise CaptureError(f"Capture id collision, refusing overwrite: {out_path}")

    body, truncated = _truncate(body)
    meta: dict[str, Any] = {
        "id": capture_id,
        "type": capture_type,
        "created_at": _now_iso(),
        "source": source,
        "status": "raw",
    }
    if truncated:
        meta["truncated"] = True
    if extra_meta:
        meta.update(extra_meta)

    post = frontmatter.Post(body if body.endswith("\n") else body + "\n", **meta)
    # frontmatter.dump writes YAML safely so body `---` does not break parsing
    out_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return out_path


def capture(
    content: str | None = None,
    *,
    type: str = "note",
    source: str | None = None,
    url: str | None = None,
    file: str | Path | None = None,
) -> Path:
    """
    Capture a note, link, or file into raw/{id}.md.

    Prefer explicit url=/file= (or CLI flags). Plain content defaults to type=note.
    """
    warnings: list[str] = []
    capture_id = _new_id()
    extra: dict[str, Any] = {}

    if url is not None or type == "link":
        link = _validate_http_url(url or content or "")
        title, warn = _fetch_url_title(link)
        if warn:
            warnings.append(warn)
        lines = [f"URL: {link}"]
        if title:
            lines.append(f"Title: {title}")
            extra["title"] = title
        if content and content.strip() and content.strip() != link:
            lines.append("")
            lines.append(content.strip())
        if warnings:
            lines.append("")
            lines.append("<!-- capture warnings -->")
            for w in warnings:
                lines.append(f"- {w}")
        path = _write_capture(
            capture_id=capture_id,
            capture_type="link",
            source=link,
            body="\n".join(lines),
            extra_meta=extra or None,
        )
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        return path

    if file is not None or type == "file":
        if file is None:
            raise CaptureError("File capture requires a path")
        path_in = _resolve_input_file(file)
        try:
            text, file_warnings = _extract_file_content(path_in)
        except CaptureError:
            raise
        warnings.extend(file_warnings)
        # Prefer project-relative source when possible (friendlier for deploy later)
        try:
            rel = path_in.relative_to(config.PROJECT_ROOT)
            source_str = rel.as_posix()
        except ValueError:
            source_str = str(path_in)

        body_parts = [
            f"File: {path_in.name}",
            f"Source: {source_str}",
            "",
        ]
        if text.strip():
            body_parts.append(text.strip())
        else:
            body_parts.append("_(No extractable text.)_")
        if warnings:
            body_parts.append("")
            body_parts.append("<!-- capture warnings -->")
            for w in warnings:
                body_parts.append(f"- {w}")

        path = _write_capture(
            capture_id=capture_id,
            capture_type="file",
            source=source_str,
            body="\n".join(body_parts),
            extra_meta={"original_filename": path_in.name},
        )
        for w in warnings:
            print(f"warning: {w}", file=sys.stderr)
        return path

    # Default: note
    note = (content or "").strip()
    if not note:
        raise CaptureError("Empty note - nothing to capture")
    return _write_capture(
        capture_id=capture_id,
        capture_type="note",
        source=source,
        body=note,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture a note, link, or file into raw/ (SecondSelf Archivist)."
    )
    parser.add_argument(
        "text",
        nargs="?",
        help="Note text (default mode). Ignored when --url/--file is set unless used as note.",
    )
    parser.add_argument("--url", help="Capture a URL as type=link")
    parser.add_argument("--file", help="Capture a local file (txt/md/pdf)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    modes = sum(bool(x) for x in (args.text, args.url, args.file))
    if modes == 0:
        parser.error("Provide note text, --url, or --file")
    if args.url and args.file:
        parser.error("Use only one of --url or --file")

    try:
        if args.url:
            out = capture(args.text, url=args.url)
        elif args.file:
            out = capture(file=args.file)
        else:
            out = capture(args.text)
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
