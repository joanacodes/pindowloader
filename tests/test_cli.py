import sys
import zipfile
from pathlib import Path

import pytest

from pindowloader import cli


# --- URL handling ---------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("https://www.pinterest.com/alice/cozy-rooms/", "https://www.pinterest.com/alice/cozy-rooms/"),
    ("https://www.pinterest.com/alice/cozy-rooms", "https://www.pinterest.com/alice/cozy-rooms"),
    ("pinterest.com/alice/cozy-rooms/", "https://pinterest.com/alice/cozy-rooms/"),
    ("https://fr.pinterest.com/alice/cozy-rooms/", "https://fr.pinterest.com/alice/cozy-rooms/"),
    ("https://www.pinterest.co.uk/alice/cozy-rooms/", "https://www.pinterest.co.uk/alice/cozy-rooms/"),
    ("https://www.pinterest.com/alice/cozy-rooms/?invite_code=abc&sender=1",
     "https://www.pinterest.com/alice/cozy-rooms/"),
    ("alice/cozy-rooms", "https://www.pinterest.com/alice/cozy-rooms/"),
    ("@alice/cozy-rooms/", "https://www.pinterest.com/alice/cozy-rooms/"),
    ("alice/cozy-rooms/kitchens", "https://www.pinterest.com/alice/cozy-rooms/kitchens/"),
    ("alice", "https://www.pinterest.com/alice/"),
    ("https://pin.it/3AbCdEf", "https://pin.it/3AbCdEf"),
    ("pin.it/3AbCdEf", "https://pin.it/3AbCdEf"),
    ("https://www.pinterest.com/pin/123456789/", "https://www.pinterest.com/pin/123456789/"),
    ("https://www.pinterest.com/search/pins/?q=blue%20tiles&rs=typed",
     "https://www.pinterest.com/search/pins/?q=blue%20tiles&rs=typed"),
    ("  https://www.pinterest.com/alice/cozy-rooms/  ", "https://www.pinterest.com/alice/cozy-rooms/"),
])
def test_normalize_url(raw, expected):
    assert cli.normalize_url(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "https://example.com/alice/board/",
    "https://notpinterest.com/alice/board/",
    "https://www.pinterest.com/",
    "ftp//nonsense",
    "example.com/alice",
])
def test_normalize_url_rejects(raw):
    with pytest.raises(cli.UsageError):
        cli.normalize_url(raw)


@pytest.mark.parametrize("raw, subcategory", [
    ("alice/cozy-rooms", "board"),
    ("https://www.pinterest.com/alice/cozy-rooms/?invite_code=x", "board"),
    ("alice/cozy-rooms/kitchens", "section"),
    ("alice", "user"),
    ("https://www.pinterest.com/pin/123456789/", "pin"),
    ("pin.it/3AbCdEf", "pinit"),
    ("https://www.pinterest.com/search/pins/?q=tiles", "search"),
    ("https://de.pinterest.com/alice/cozy-rooms/", "board"),
])
def test_gallery_dl_recognises_normalized_urls(raw, subcategory):
    """The URLs we hand over must hit the intended gallery-dl extractor."""
    extractor = pytest.importorskip("gallery_dl.extractor")
    ex = extractor.find(cli.normalize_url(raw))
    assert ex is not None
    assert ex.category == "pinterest"
    assert ex.subcategory == subcategory


def test_read_url_file(tmp_path):
    f = tmp_path / "boards.txt"
    f.write_text(
        "# my boards\n"
        "\n"
        "alice/cozy-rooms   # living room ideas\n"
        "https://www.pinterest.com/bob/garden/\n"
        "https://www.pinterest.com/bob/garden/#related\n",
        encoding="utf-8",
    )
    assert cli.read_url_file(f) == [
        "alice/cozy-rooms",
        "https://www.pinterest.com/bob/garden/",
        "https://www.pinterest.com/bob/garden/#related",
    ]


def test_read_url_file_missing(tmp_path):
    with pytest.raises(cli.UsageError):
        cli.read_url_file(tmp_path / "nope.txt")


# --- command building -----------------------------------------------------

def _args(*argv):
    return cli.build_parser().parse_args(list(argv))


def test_build_command_defaults():
    args = _args("alice/board")
    cmd = cli.build_command(args, ["https://www.pinterest.com/alice/board/"])
    assert cmd == [
        sys.executable, "-m", "gallery_dl",
        "--destination", "pins",
        "https://www.pinterest.com/alice/board/",
    ]


def test_build_command_all_options(tmp_path):
    cookies = tmp_path / "cookies.txt"
    args = _args(
        "x", "-o", str(tmp_path / "out"), "--browser", "firefox", "--profile", "work",
        "--cookies", str(cookies), "-n", "50", "--no-videos", "--no-sections",
        "--metadata", "--sleep", "1.5", "-q",
    )
    cmd = cli.build_command(args, ["U"])
    assert cmd[:3] == [sys.executable, "-m", "gallery_dl"]
    joined = " ".join(cmd)
    assert f"--destination {tmp_path / 'out'}" in joined
    assert "--cookies-from-browser firefox:work" in joined
    assert f"--cookies {cookies}" in joined
    assert "--range 1-50" in joined
    assert "--option extractor.pinterest.videos=false" in joined
    assert "--option extractor.pinterest.sections=false" in joined
    assert "--write-metadata" in cmd
    assert "--sleep 1.5" in joined
    assert "--quiet" in cmd
    assert cmd[-1] == "U"


def test_build_command_list_mode():
    args = _args("x", "--list", "--metadata")
    cmd = cli.build_command(args, ["U"])
    assert "--get-urls" in cmd
    assert "--destination" not in cmd
    assert "--write-metadata" not in cmd


def test_gallery_dl_accepts_built_flags(tmp_path):
    """gallery-dl's own parser must accept every flag we generate."""
    option = pytest.importorskip("gallery_dl.option")
    cookies = tmp_path / "cookies.txt"
    args = _args(
        "x", "--browser", "firefox", "--profile", "p", "--cookies", str(cookies),
        "-n", "5", "--no-videos", "--no-sections", "--metadata", "--sleep", "2", "-q",
    )
    cmd = cli.build_command(args, ["https://www.pinterest.com/a/b/"])
    parsed = option.build_parser().parse_args(cmd[3:])
    assert parsed.urls == ["https://www.pinterest.com/a/b/"]


# --- main() ---------------------------------------------------------------

def test_main_dry_run(capsys):
    assert cli.main(["alice/board", "alice/board", "--dry-run"]) == 0
    out = capsys.readouterr().out
    # duplicates are dropped
    assert out.count("https://www.pinterest.com/alice/board/") == 1
    assert "gallery_dl" in out


def test_main_requires_url():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_main_rejects_non_pinterest():
    with pytest.raises(SystemExit) as exc:
        cli.main(["https://example.com/a/b"])
    assert exc.value.code == 2


def test_main_profile_needs_browser():
    with pytest.raises(SystemExit):
        cli.main(["alice/board", "--profile", "x"])


def test_main_list_and_zip_conflict():
    with pytest.raises(SystemExit):
        cli.main(["alice/board", "--list", "--zip"])


def test_main_missing_cookie_file(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["alice/board", "--cookies", str(tmp_path / "missing.txt")])


def test_main_runs_gallery_dl_and_zips(tmp_path, monkeypatch):
    out = tmp_path / "pins"
    calls = []

    def fake_call(cmd):
        calls.append(cmd)
        board = out / "pinterest" / "alice" / "board"
        board.mkdir(parents=True)
        (board / "pinterest_1.jpg").write_bytes(b"jpg")
        (board / "pinterest_2.png").write_bytes(b"png")
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert cli.main(["alice/board", "-o", str(out), "--zip", "-q"]) == 0
    assert len(calls) == 1 and calls[0][-1] == "https://www.pinterest.com/alice/board/"

    archive = tmp_path / "pins.zip"
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == [
            "pins/pinterest/alice/board/pinterest_1.jpg",
            "pins/pinterest/alice/board/pinterest_2.png",
        ]


def test_main_zip_with_nothing_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: 4)
    assert cli.main(["alice/board", "-o", str(tmp_path / "pins"), "--zip"]) == 4
    assert not (tmp_path / "pins.zip").exists()


def test_main_passes_through_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: 1)
    assert cli.main(["alice/board", "-o", str(tmp_path)]) == 1


def test_zip_folder_dotted_name(tmp_path):
    folder = tmp_path / "my.pins"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"x")
    assert cli.zip_folder(folder) == (tmp_path / "my.pins.zip").resolve()


def test_module_entry_point():
    import runpy
    with pytest.raises(SystemExit) as exc:
        sys.argv = ["pindowloader", "--version"]
        runpy.run_module("pindowloader", run_name="__main__")
    assert exc.value.code == 0
