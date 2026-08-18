from system import enable_dpi_awareness
import argparse
import compactor
import config
import json
import os
import player
import recorder
import time


def save_macro(steps: list, path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w") as f:
        json.dump({"version": 1, "steps": steps}, f, indent=2)

    print("saved %s steps to %s" % (len(steps), path))


def load(path: str, key: str) -> list:
    with open(path) as f:
        return json.load(f)[key]


def summarise(step: dict) -> str:
    kind = step["type"]

    if kind == "wait":
        return "%s ms%s" % (step["ms"], "  (%s)" % step["note"] if "note" in step else "")
    if kind == "type_text":
        return repr(step["text"])
    if kind in ("key_press", "key_down", "key_up"):
        return step["key"]
    if kind == "move":
        return "%s -> %s   %s pts" % (step["from"], step["to"], len(step.get("path", [])))
    if kind == "scroll":
        return "dx %s  dy %s   at (%s, %s)" % (step["dx"], step["dy"], step["x"], step["y"])
    if kind in ("click", "mouse_down", "mouse_up"):
        return "%s at (%s, %s)" % (step["button"], step["x"], step["y"])

    return ""


def show(steps: list):
    for n, step in enumerate(steps):
        print("%4d  %7.2f  %-11s %s"
              % (n, step.get("t_start", 0), step["type"], summarise(step)))

    print("\n%s steps" % len(steps))


def countdown(action: str):
    for remaining in range(config.COUNTDOWN_SECONDS, 0, -1):
        print("%s in %s..." % (action, remaining))
        time.sleep(1)


def cmd_record(args):
    """Record, compact, and write both the raw log and the macro."""
    events = recorder.record()
    recorder.save(events, config.RECORDING_PATH)

    steps = compactor.compact(events)
    save_macro(steps, config.MACRO_PATH)
    show(steps)


def cmd_compact(args):
    """Rebuild the macro from the raw log, picking up any config changes."""
    events = load(config.RECORDING_PATH, "events")
    steps = compactor.compact(events)

    print("%s events -> %s steps" % (len(events), len(steps)))
    save_macro(steps, config.MACRO_PATH)


def cmd_show(args):
    show(load(config.MACRO_PATH, "steps"))


def cmd_play(args):
    steps = load(config.MACRO_PATH, "steps")

    print("%s steps, press %s to abort" % (len(steps), config.ABORT_KEY))
    countdown("replaying")

    print("done" if player.play(steps, args.speed) else "aborted")


def main():
    parser = argparse.ArgumentParser(description="record, compact and replay input macros")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("record", help="record input and write a macro").set_defaults(run=cmd_record)
    commands.add_parser("compact", help="rebuild the macro from the raw log").set_defaults(run=cmd_compact)
    commands.add_parser("show", help="print the macro's steps").set_defaults(run=cmd_show)

    play = commands.add_parser("play", help="replay the macro")
    play.add_argument("--speed", type=float, default=None, help="1.0 is recorded speed")
    play.set_defaults(run=cmd_play)

    args = parser.parse_args()
    enable_dpi_awareness()
    args.run(args)


if __name__ == "__main__":
    main()
