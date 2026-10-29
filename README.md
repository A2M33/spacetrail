<p align="center"><img src="docs/header.svg" alt="spacetrail" width="100%"></p>

<p align="center">
  <a href="https://github.com/A2M33/spacetrail/actions/workflows/test.yml"><img alt="tests" src="https://github.com/A2M33/spacetrail/actions/workflows/test.yml/badge.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab">
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-3fb950">
  <a href="https://github.com/A2M33/spacetrail/blob/main/LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-3fb950"></a>
</p>

Your drive was fine last week and now it's full. spacetrail tells you which folders ate the space.

Once a day it records how big each folder is. Ask it later and it compares today with a week ago, then lists the folders that grew, down to the one responsible: your `Downloads`, Chrome's cache, a game update or Windows Update leftovers.

![spacetrail showing which folders grew in the last 7 days](docs/demo.png)

*Example output on a test drive.*

WinDirStat and WizTree show what's big today. They have no memory of last week, so the 40 GB game you installed two years ago tops their list while the 9 GB that arrived on Tuesday hides further down.

## Install

**Windows, no Python needed.** Download `spacetrail.exe` from the [latest release](https://github.com/A2M33/spacetrail/releases/latest) and put it in a folder that stays put, like `C:\Tools`, before you run `spacetrail schedule`. The daily task remembers where the file lives. Double-clicking it shows the weekly report.

Windows SmartScreen may warn you the first time because the file isn't code-signed. Click "More info", then "Run anyway". GitHub Actions builds the file from this repository's code on every release.

**With Python 3.10 or newer** (Windows, Linux, macOS):

```bash
pip install git+https://github.com/A2M33/spacetrail
```

## Use

```bash
spacetrail schedule   # take a snapshot every day (Windows Task Scheduler or cron)
spacetrail            # what grew in the last 7 days
```

Run without any history, `spacetrail` takes a baseline snapshot. You get your first report after the second snapshot.

| Command | What it does |
| --- | --- |
| `spacetrail` | Report changes since about a week ago |
| `spacetrail --since 1d` | Compare with yesterday (`12h`, `3d`, `2w` and `1m` also work) |
| `spacetrail --fresh` | Take a snapshot now, then report. Good when the disk *just* filled up |
| `spacetrail --min 1GB` | Hide changes smaller than 1 GB (default 100 MB) |
| `spacetrail snap D:\ E:\` | Snapshot other drives or folders |
| `spacetrail report D:\` | Report on one of them |
| `spacetrail list` | Show saved snapshots |
| `spacetrail schedule --time 09:00` | Change the daily time (default 12:30) |
| `spacetrail unschedule` | Remove the daily task |

By default it scans the system drive on Windows (`C:\`) and your home folder on Linux and macOS.

## How it works

- **Scanning.** spacetrail walks the drive and adds up file sizes. On my machine a full `C:\` with 800,000 files takes 10 to 30 seconds. It skips junctions and symlinks so it never counts a file twice, and on Linux it also skips other mounted drives and `/proc`-style folders. It counts the folders Windows won't let it read and moves on.
- **Storage.** spacetrail writes folder sizes up to six levels deep into a SQLite file at `%LOCALAPPDATA%\spacetrail\snapshots.db` on Windows or `~/.local/share/spacetrail/` on Linux and macOS. Deeper folders add to their parent at level six. It leaves out folders under 1 MB, which keeps a full-drive snapshot near 1 MB, and it deletes snapshots older than 90 days (change that with `--keep`).
- **Finding the culprit.** Say `Users` grew by 10 GB and 9 GB of that sits in `Users\you\Downloads`. Listing all three folders adds noise, so spacetrail shows a folder only when the subfolders already on the list explain less than 80% of its growth.
- **Daily runs.** The Windows task uses "run as soon as possible after a missed start", so a laptop that was off at 12:30 still gets its snapshot once you turn it on. It starts through `pythonw`, which means no console window flashes up.

## Development

```bash
git clone https://github.com/A2M33/spacetrail
cd spacetrail
pip install -e ".[dev]"
pytest
```

GitHub Actions runs the tests on Windows, Linux and macOS.

## License

MIT
