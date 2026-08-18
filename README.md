
# PyReplay

A free open-source macro recorder and editor made with python. 


## Features

- Open-source & free 
- Runs locally
- Record keystrokes, mouse clicks, & mouse movements
- Actions are translated into editable blocks for finetuning
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
uv run main.py record     # record, then compact and save
uv run main.py show       # print the macro's steps
uv run main.py play       # replay it
uv run main.py compact    # rebuild the macro from the raw recording
```

While recording, `F10` pauses and `F9` stops. During playback `F9` aborts.
Both keys, along with every threshold below, live in `config.py`.

Two files are written:

| file | what it holds |
| --- | --- |
| `outputs/recording.json` | the raw event log, every mouse move and keypress |
| `outputs/macro.json` | the compacted steps, meant to be read and edited |

> Recording captures **everything** typed while it runs, passwords included.
> Recordings stay out of git by default. Use `F10` to pause before typing
> anything you would not want saved to disk.


## How it works

Recording produces a few thousand raw events. A pass of matchers turns those
into steps, and only then is anything worth editing:

```
record   ->  raw events (~4500)      the tape
compact  ->  steps (~90)             the macro, editable
play     ->  performs the steps
```

Each matcher claims a pattern in the event stream — a quick press and release
becomes a `click`, a run of characters becomes `type_text`, a run of movement
becomes a `move` with its path thinned to the points that describe its shape.
Anything no matcher recognises falls back to the raw press and release, so an
unusual gesture comes out verbose rather than wrong.

`compact` re-runs that pass over a recording you already have, so the
thresholds in `config.py` can be tuned without recording again.


## Roadmap

- UI to edit & view steps
- Image & text matching w/ OCR
- Post-playback options
- Scheduling

