# pindowloader

Download every pin from a Pinterest board at original resolution, not just
the first 25 that load on the page.

It works with boards, board sections, single pins, `pin.it` short links, a
user's whole profile and pin searches. Under the hood it uses
[gallery-dl](https://github.com/mikf/gallery-dl), which talks to Pinterest's
internal API, pages through the whole board, and picks the right file type
for each original image (no 403s from guessing `.jpg` vs `.png`).

## Install

You need Python 3.9 or newer.

```bash
pip install git+https://github.com/joanacodes/pindowloader
```

Or from a clone:

```bash
git clone https://github.com/joanacodes/pindowloader
cd pindowloader
pip install .
```

## Use

```bash
pindowloader https://www.pinterest.com/USERNAME/BOARD-NAME/
```

Files land in `./pins/pinterest/USERNAME/BOARD-NAME/`. Run the same command
later and it only fetches the pins you don't have yet.

You can skip the `https://www.pinterest.com/` part:

```bash
pindowloader USERNAME/BOARD-NAME
```

### Common recipes

| What you want | Command |
| --- | --- |
| Save somewhere else | `pindowloader USER/BOARD -o ~/Pictures/pins` |
| Get one zip file at the end | `pindowloader USER/BOARD --zip` (makes `pins.zip`) |
| A private or secret board | `pindowloader USER/BOARD --browser firefox` |
| Only one section of a board | `pindowloader USER/BOARD/SECTION` |
| Every board a user has | `pindowloader USER` |
| Just try the first 20 | `pindowloader USER/BOARD -n 20` |
| Images only, no videos | `pindowloader USER/BOARD --no-videos` |
| Board without its sections | `pindowloader USER/BOARD --no-sections` |
| Keep titles, descriptions and links | `pindowloader USER/BOARD --metadata` |
| Many boards at once | `pindowloader -f boards.txt` |
| Only list the image URLs | `pindowloader USER/BOARD --list > urls.txt` |
| See what would run | `pindowloader USER/BOARD --dry-run` |

`boards.txt` holds one URL (or `USER/BOARD`) per line. Lines starting with
`#` are ignored, and so is anything after ` #` on a line.

Run `pindowloader --help` for every option.

### Private and secret boards

Pinterest only shows these to a logged-in account, so pindowloader borrows
the login session from your browser:

```bash
pindowloader USER/BOARD --browser firefox
```

`chrome`, `edge`, `brave`, `chromium`, `opera`, `vivaldi` and `safari` also
work. Use `--profile NAME` if you have several browser profiles. Firefox is
the most reliable. Recent Chrome and Edge on Windows encrypt their cookies in
a way that often can't be read. If that happens, export a `cookies.txt` with a
browser extension (Netscape format) and use:

```bash
pindowloader USER/BOARD --cookies cookies.txt
```

Keep `cookies.txt` private, because it logs in as you.

### Exit codes

`0` means everything downloaded. Any other code is passed through from
gallery-dl and means some pins failed: usually a private board without
cookies, a mistyped URL, or a network problem. `2` means the command itself
was wrong (bad option, or not a Pinterest URL).

## Use responsibly

Download boards you have the right to use, such as your own saves or for
personal reference. Pinterest's terms don't allow bulk redistribution of
other people's images.

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests don't need network access. Among other things they check that
every URL form pindowloader produces is routed to the right gallery-dl
Pinterest extractor, and that gallery-dl accepts every flag it builds.
