"""Command-line interface for pindowloader.

pindowloader is a thin, friendly front end for gallery-dl's Pinterest
support. gallery-dl does the hard part (talking to Pinterest's internal API,
paging through every pin, picking the original-resolution file). This module
turns simple options into the right gallery-dl command, runs it, and can zip
the result.
"""

from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from . import __version__

BROWSERS = ("firefox", "chrome", "chromium", "edge", "brave", "opera", "vivaldi", "safari")

_PINTEREST_HOST = re.compile(r"^(?:[\w-]+\.)*pinterest\.[a-z.]+$", re.IGNORECASE)
_PINIT_HOST = re.compile(r"^pin\.it$", re.IGNORECASE)
_SHORTHAND = re.compile(r"^@?[\w.-]+(?:/[\w%.-]+){0,2}/?$")


class UsageError(Exception):
    """Raised for bad input that should be reported without a traceback."""


def normalize_url(raw: str) -> str:
    """Turn user input into a URL gallery-dl's Pinterest extractors accept.

    Accepts full URLs, URLs without a scheme (``pinterest.com/user/board``),
    ``pin.it`` short links and the shorthand ``user/board`` or
    ``user/board/section``.
    """
    text = raw.strip()
    if not text:
        raise UsageError("empty URL")

    if "://" not in text:
        host = text.split("/", 1)[0]
        if _PINTEREST_HOST.match(host) or _PINIT_HOST.match(host):
            text = "https://" + text
        elif _SHORTHAND.match(text) and "." not in host:
            path = text.lstrip("@").strip("/")
            return f"https://www.pinterest.com/{path}/"
        else:
            raise UsageError(f"not a Pinterest URL: {raw!r}")

    match = re.match(r"^(https?)://([^/?#]+)(.*)$", text, re.IGNORECASE)
    if not match:
        raise UsageError(f"not a Pinterest URL: {raw!r}")
    host, rest = match.group(2), match.group(3)

    if _PINIT_HOST.match(host):
        return f"https://pin.it{rest}"
    if not _PINTEREST_HOST.match(host):
        raise UsageError(f"not a Pinterest URL: {raw!r}")

    path, _, query = rest.partition("?")
    path, _, fragment = path.partition("#")
    if fragment == "related":
        path += "#related"
    # Keep the query string only for searches, where it carries the terms.
    if path.rstrip("/").endswith("/search/pins") and query:
        return f"https://{host}{path}?{query.split('#', 1)[0]}"
    if not path or path == "/":
        raise UsageError(f"URL has no board, user or pin in it: {raw!r}")
    return f"https://{host}{path}"


def read_url_file(path: Path) -> List[str]:
    """Read URLs from a text file: one per line, ``#`` starts a comment."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc.strerror or exc}") from exc
    urls = []
    for line in lines:
        # A comment is a whole line starting with '#', or ' #' after a URL.
        # A bare '#' inside a URL (like '#related') is kept.
        line = line.split(" #", 1)[0].strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def build_command(args: argparse.Namespace, urls: Sequence[str]) -> List[str]:
    """Build the gallery-dl command line for the parsed options."""
    cmd = [sys.executable, "-m", "gallery_dl"]

    if args.list:
        cmd.append("--get-urls")
    else:
        cmd += ["--destination", str(args.output)]

    if args.browser:
        spec = args.browser
        if args.profile:
            spec += f":{args.profile}"
        cmd += ["--cookies-from-browser", spec]
    if args.cookies:
        cmd += ["--cookies", str(args.cookies)]

    if args.limit:
        cmd += ["--range", f"1-{args.limit}"]
    if args.no_videos:
        cmd += ["--option", "extractor.pinterest.videos=false"]
    if args.no_sections:
        cmd += ["--option", "extractor.pinterest.sections=false"]
    if args.metadata and not args.list:
        cmd.append("--write-metadata")
    if args.sleep:
        cmd += ["--sleep", str(args.sleep)]
    if args.quiet:
        cmd.append("--quiet")

    cmd += list(urls)
    return cmd


def zip_folder(folder: Path, destination: Optional[Path] = None) -> Path:
    """Zip everything under ``folder`` into ``destination`` (default: folder.zip)."""
    folder = folder.resolve()
    destination = (destination or folder.parent / f"{folder.name}.zip").resolve()
    files = sorted(p for p in folder.rglob("*") if p.is_file() and p != destination)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as zf:
        # Images and videos are already compressed; storing them is faster
        # and the archive comes out the same size.
        for file in files:
            zf.write(file, file.relative_to(folder.parent))
    return destination


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _non_negative_float(value: str) -> float:
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pindowloader",
        description=(
            "Download every pin from Pinterest boards, sections, single pins or "
            "a user's whole profile, at original resolution."
        ),
        epilog=(
            "examples:\n"
            "  pindowloader https://www.pinterest.com/USER/BOARD/\n"
            "  pindowloader USER/BOARD --zip\n"
            "  pindowloader USER/BOARD --browser firefox   # private/secret boards\n"
            "  pindowloader -f boards.txt -o ~/Pictures/pins\n"
            "\n"
            "Running the same command again only downloads pins you don't have yet."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "urls", nargs="*", metavar="URL",
        help="board, section, pin, pin.it, profile or search URL; "
             "'USER/BOARD' shorthand also works",
    )
    parser.add_argument(
        "-f", "--file", type=Path, metavar="FILE",
        help="read URLs from FILE, one per line ('#' starts a comment)",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("pins"), metavar="DIR",
        help="folder to save into (default: ./pins). Files go to "
             "DIR/pinterest/USER/BOARD/",
    )
    parser.add_argument(
        "--browser", choices=BROWSERS, metavar="NAME",
        help="use your logged-in session from this browser, for private or secret "
             "boards (" + ", ".join(BROWSERS) + "). Firefox is the most reliable; "
             "recent Chrome on Windows often can't be read, use --cookies instead",
    )
    parser.add_argument(
        "--profile", metavar="NAME",
        help="browser profile to take cookies from (with --browser)",
    )
    parser.add_argument(
        "--cookies", type=Path, metavar="FILE",
        help="load cookies from a Netscape cookies.txt file",
    )
    parser.add_argument(
        "-n", "--limit", type=_positive_int, metavar="N",
        help="only download the first N files",
    )
    parser.add_argument(
        "--no-videos", action="store_true",
        help="skip video pins",
    )
    parser.add_argument(
        "--no-sections", action="store_true",
        help="don't descend into a board's sections",
    )
    parser.add_argument(
        "--metadata", action="store_true",
        help="also save each pin's details (title, description, link) as JSON",
    )
    parser.add_argument(
        "--zip", action="store_true",
        help="when done, pack the output folder into DIR.zip",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="print the media URLs instead of downloading them",
    )
    parser.add_argument(
        "--sleep", type=_non_negative_float, metavar="SECONDS",
        help="wait this long before each download, to go easy on Pinterest",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="only print errors",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show the gallery-dl command that would run, then stop",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}",
    )
    return parser


def collect_urls(args: argparse.Namespace) -> List[str]:
    raw: List[str] = list(args.urls)
    if args.file:
        raw += read_url_file(args.file)
    if not raw:
        raise UsageError("give at least one URL, or a file of URLs with --file")
    seen = set()
    urls = []
    for item in raw:
        url = normalize_url(item)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _check_gallery_dl() -> None:
    try:
        import gallery_dl  # noqa: F401
    except ImportError as exc:
        raise UsageError(
            "gallery-dl is not installed. Install it with:  pip install gallery-dl"
        ) from exc


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(None if argv is None else list(argv))

    try:
        if args.profile and not args.browser:
            raise UsageError("--profile needs --browser")
        if args.list and args.zip:
            raise UsageError("--list prints URLs and downloads nothing, so it can't be combined with --zip")
        if args.cookies and not args.cookies.is_file():
            raise UsageError(f"cookies file not found: {args.cookies}")
        urls = collect_urls(args)
        args.output = args.output.expanduser()
        cmd = build_command(args, urls)

        if args.dry_run:
            print(shlex.join(cmd))
            return 0

        _check_gallery_dl()
    except UsageError as exc:
        parser.error(str(exc))  # exits with status 2

    if not args.list and not args.quiet:
        print(f"Downloading {len(urls)} URL(s) into {args.output.resolve()}", file=sys.stderr)

    try:
        returncode = subprocess.call(cmd)
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to pick up where it left off.", file=sys.stderr)
        return 130

    if returncode != 0 and not args.quiet:
        print(
            f"gallery-dl finished with errors (exit code {returncode}). "
            "Some pins may be missing; private boards need --browser or --cookies.",
            file=sys.stderr,
        )

    if args.zip:
        if args.output.is_dir() and any(p.is_file() for p in args.output.rglob("*")):
            archive = zip_folder(args.output)
            if not args.quiet:
                print(f"Zipped into {archive}", file=sys.stderr)
        else:
            print("Nothing was downloaded, so no zip was made.", file=sys.stderr)
            return returncode or 1

    return returncode
