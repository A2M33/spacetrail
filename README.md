# spacetrail

```
PS> spacetrail
X:\   Nov 15, 12:36 (7 days ago)  ->  Nov 22, 12:36 (today)
  folder size 27.3 GB (+4.9 GB)   free space 47.2 GB -> 42.1 GB

  Grew
     +2.3 GB  ██████████        new -> 2.3 GB     Program Files (x86)\Steam\steamapps\common\Hades II
     +1.7 GB  ███████      210.0 MB -> 1.9 GB     Users\amin\Downloads
   +610.0 MB  ███          140.0 MB -> 750.0 MB   Users\amin\AppData\Local\Google\Chrome
              Browser data, mostly cache. In the browser: Settings > Privacy > Clear browsing data > Cached images and files.
   +460.0 MB  ██                new -> 460.0 MB   Windows\SoftwareDistribution\Download
              Windows Update downloads. Disk Cleanup > Clean up system files > Windows Update Cleanup.
   +380.0 MB  ██                new -> 380.0 MB   Users\amin\AppData\Local\Temp\installer_tmp
              Temporary files. Settings > System > Storage > Temporary files, or delete what's over a week old.
   +290.0 MB  █                 new -> 290.0 MB   Program Files (x86)\Steam\steamapps\downloading

  Shrank
   -830.0 MB  ██████████   830.0 MB -> deleted    Users\amin\Videos\Captures
```

*The report for two made-up snapshots of a test drive, taken a week apart. [tools/demo/make_demo.py](tools/demo/make_demo.py) runs spacetrail on them and prints this output.*

spacetrail records how big each folder on your drive is, once a day. When the drive fills up, run `spacetrail` and it compares today with a week ago. You get the folders that grew, down to the one responsible: your `Downloads`, Chrome's cache, a game update or Windows Update leftovers.

WinDirStat and WizTree show what's big today. They have no memory of last week, so the 40 GB game you installed two years ago tops their list while the 9 GB that arrived on Tuesday sits further down.

## Install

**Windows, no Python needed.** Download `spacetrail.exe` from the [latest release](https://github.com/A2M33/spacetrail/releases/latest) and put it in a folder that stays put, like `C:\Tools`, before you run `spacetrail schedule`. The daily task remembers where the file lives. The first double-click scans your drive, lists the biggest folders and asks if you want a snapshot every day. After that, a double-click shows the weekly report.

Windows SmartScreen may warn you the first time because the file isn't code-signed. Click "More info", then "Run anyway". GitHub Actions builds the file from this repository's code for each release.

**With Python 3.10 or newer** (Windows, Linux, macOS). spacetrail needs nothing outside the standard library.

```bash
pip install git+https://github.com/A2M33/spacetrail
```

## Use

```bash
spacetrail schedule   # take a snapshot every day (Windows Task Scheduler or cron)
spacetrail            # what grew in the last 7 days
```

The first run scans all of `C:\` (your home folder on Linux and macOS) and takes 10 to 30 seconds. It then lists the ten biggest folders. Your first report of what grew comes after the second snapshot.

Each snapshot ends with a line like `Saved C:\: 212.4 GB in 801,233 files (19s, 412 folders not readable)`. Without admin rights you will see some unreadable folders, because Windows keeps some system folders private. spacetrail counts them and moves on. Run it from an admin terminal if you want them included.

| Command | What it does |
| --- | --- |
| `spacetrail` | Report changes since about a week ago |
| `spacetrail --since 1d` | Compare with yesterday (`12h`, `3d`, `2w` and `1m` also work) |
| `spacetrail --fresh` | Take a new snapshot first, then report. Use it when the disk filled up today |
| `spacetrail --min 1GB` | Hide changes smaller than 1 GB (default 100 MB) |
| `spacetrail report C:\Users\you` | Show only what changed inside one folder of a snapshot |
| `spacetrail top` | List the biggest folders in the latest snapshot, with cleanup tips |
| `spacetrail top C:\Users\you -n 30` | The 30 biggest folders inside one folder |
| `spacetrail --json`, `spacetrail top --json` | Print UTF-8 JSON for scripts |
| `spacetrail snap D:\ E:\` | Snapshot other drives or folders |
| `spacetrail report D:\` | Report on one of them |
| `spacetrail list` | Show saved snapshots |
| `spacetrail schedule --time 09:00` | Change the daily time (default 12:30) |
| `spacetrail unschedule` | Remove the daily task |

## Cleanup tips

`spacetrail top` and the report print a one-line tip under folders that often fill disks: the temp folder, Windows Update downloads (`Windows\SoftwareDistribution\Download`), browser caches, `node_modules`, the Recycle Bin, and the pip and npm caches. The tip says how to get the space back, like `pip cache purge` or the right page in Windows Settings. spacetrail deletes nothing itself. You decide what to clear.

## How it works

spacetrail walks the drive and adds up file sizes. On my machine a full `C:\` with 800,000 files takes 10 to 30 seconds. It skips junctions and symlinks so it doesn't count a file twice, but it does count OneDrive folders. On Linux it also skips other mounted drives and `/proc`-style folders.

It writes folder sizes up to six levels deep into a SQLite file: `%LOCALAPPDATA%\spacetrail\snapshots.db` on Windows, `~/.local/share/spacetrail/` on Linux and macOS. A folder deeper than that counts toward its parent at level six. `--depth` changes the limit, and if two snapshots used different depths, spacetrail compares them at the shallower one. It leaves out folders under 1 MB, so a full-drive snapshot stays near 1 MB, and it deletes snapshots older than 90 days (change that with `--keep`).

To pick which folders to show, say `Users` grew by 10 GB and 9 GB of that sits in `Users\you\Downloads`. Listing all three folders adds noise. spacetrail shows a folder only when the subfolders already on the list explain less than 80% of its growth.

The Windows task uses "run as soon as possible after a missed start". A laptop that was off at 12:30 gets its snapshot once you turn it on. With Python installed the task starts spacetrail through `pythonw`, which opens no window. `spacetrail.exe` is a console program, so Windows opens a window for it, and spacetrail hides that window within a second of starting.

## Development

```bash
git clone https://github.com/A2M33/spacetrail
cd spacetrail
pip install -e ".[dev]"
pytest
```

GitHub Actions runs the tests on Windows, Linux and macOS.

To print the sample report at the top of this page again, run `python tools/demo/make_demo.py`.

## License

MIT
