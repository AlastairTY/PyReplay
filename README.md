
# PyReplay

A free open-source macro recorder and editor made with python. 


## Features

- Open-source & free 
- Runs locally
- Record keystrokes, mouse clicks, & mouse movements
- Actions are translated into editable blocks for finetuning
- Editor to reorder, rename, disable, & hand-write steps
- Record extra steps into the middle of an existing macro
- Replay & repeat macros
- Save macros as files (JSON)


## Demo

WIP


## Installation

Windows, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```
git clone https://github.com/AlastairTY/pyreplay
cd pyreplay
uv sync
```


## Usage

```
uv run main.py
```

That opens the editor. Record from the toolbar, and the steps appear in the
list when you stop. From there you can rename them, switch them off, reorder
them by dragging, cut and paste them, and insert waits or clicks by hand.
`Insert > Recording` records straight into the middle of an existing macro.

There is also a CLI, mostly for replaying a saved macro without opening a
window:

```
uv run main.py play macros/login.json
uv run main.py play macros/login.json --speed 2
uv run main.py record     # record and save without the editor
uv run main.py show       # print the steps
uv run main.py compact    # rebuild a macro from the raw recording
```

While recording, `F10` pauses and `F9` stops. During playback `F9` aborts.
Both keys live in `config.py`, along with the compaction thresholds.

Macros are JSON and are saved wherever you point the editor, `macros/` by
default. Two more files live in `outputs/`:

| file | what it holds |
| --- | --- |
| `outputs/recording.json` | the raw event log from the last recording |
| `outputs/macro.json` | the steps the CLI reads when you do not name a macro |

> Recording captures **everything** typed while it runs, passwords included.
> Recordings stay out of git by default. Use `F10` to pause before typing
> anything you would not want saved to disk.


## How it works

A recording is a few thousand raw events. Matchers turn those into a short
list of steps you can read and edit:

```
record   ->  raw events (~4500)      the tape
compact  ->  steps (~90)             the macro, editable
play     ->  performs the steps
```

Each matcher claims a pattern in the event stream: a quick press and release
becomes a `click`, a run of characters becomes `type_text`, and a run of
movement becomes a `move` with its path thinned to the points that describe
its shape. Anything no matcher recognises falls back to the raw press and
release, so an unusual gesture comes out verbose rather than wrong.

`compact` re-runs that pass over a recording you already have, so you can tune
the thresholds in `config.py` without recording again.


## Roadmap

- Image & text matching w/ OCR
- Post-playback options
- Scheduling

