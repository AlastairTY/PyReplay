from system import enable_dpi_awareness
import argparse
import compactor
import config
import macro
import os
import player
import recorder
import time


def save(steps: list, path: str):
    macro.save(steps, path)
    print("saved %s steps to %s" % (len(steps), path))


def show(steps: list):
    disabled = 0
    for n, step in enumerate(steps):
        off = not step.get("enabled", True)
        disabled += off

        print("%4d %s %7.2f  %-11s %-34s %s"
              % (n, "x" if off else " ", step.get("t_start", 0), step["type"],
                 macro.summarise(step), step.get("name", "")))

    print("\n%s steps%s" % (len(steps), ", %s disabled" % disabled if disabled else ""))


def countdown(action: str):
    for remaining in range(config.COUNTDOWN_SECONDS, 0, -1):
        print("%s in %s..." % (action, remaining))
        time.sleep(1)


def cmd_record(args):
    """Record, compact, and write both the raw log and the macro."""
    events = recorder.record()
    recorder.save(events, config.RECORDING_PATH)

    steps = compactor.compact(events)
    save(steps, config.MACRO_PATH)
    show(steps)


def cmd_compact(args):
    """Rebuild the macro from the raw log, picking up any config changes."""
    # neither field is written by the compactor, so either one means somebody
    # has been in the file and rebuilding it would throw their work away
    existing = macro.load(config.MACRO_PATH) if os.path.exists(config.MACRO_PATH) else []
    if not args.force and any(("name" in step) or ("enabled" in step) for step in existing):
        print("%s has edits that re-compacting would discard, pass --force"
              % config.MACRO_PATH)
        return

    events = macro.load(config.RECORDING_PATH, "events")
    steps = compactor.compact(events)

    print("%s events -> %s steps" % (len(events), len(steps)))
    save(steps, config.MACRO_PATH)


def cmd_show(args):
    show(macro.load(config.MACRO_PATH))


def cmd_ui(args):
    import ui   # imported late so the CLI does not pull in Qt
    ui.run()


def cmd_play(args):
    steps = macro.load(args.macro or config.MACRO_PATH)

    print("%s steps, press %s to abort" % (len(steps), config.ABORT_KEY))
    countdown("replaying")

    print("done" if player.play(steps, args.speed) else "aborted")


def main():
    parser = argparse.ArgumentParser(description="record, compact and replay input macros")
    commands = parser.add_subparsers(dest="command")

    # no subcommand opens the editor, which is the usual way in
    parser.set_defaults(run=cmd_ui)

    commands.add_parser("record", help="record input and write a macro").set_defaults(run=cmd_record)
    compact = commands.add_parser("compact", help="rebuild the macro from the raw log")
    compact.add_argument("--force", action="store_true", help="overwrite a macro with edits")
    compact.set_defaults(run=cmd_compact)
    commands.add_parser("show", help="print the macro's steps").set_defaults(run=cmd_show)
    commands.add_parser("ui", help="open the editor").set_defaults(run=cmd_ui)

    play = commands.add_parser("play", help="replay a macro")
    play.add_argument("macro", nargs="?", help="path to a macro, or the last one recorded")
    play.add_argument("--speed", type=float, default=None, help="1.0 is recorded speed")
    play.set_defaults(run=cmd_play)

    args = parser.parse_args()
    enable_dpi_awareness()
    args.run(args)


if __name__ == "__main__":
    main()
