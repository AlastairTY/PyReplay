from pynput import keyboard, mouse
from system import enable_dpi_awareness
import config
import json
import os
import time


STOP_KEY = keyboard.Key[config.STOP_KEY.lower()]
PAUSE_KEY = keyboard.Key[config.PAUSE_KEY.lower()]


def key_to_str(key) -> str:
    """
    Name a key in a way that survives json and can be turned back into a key.

    pynput hands back a Key member for named keys like shift and enter, and a
    KeyCode for everything else. A KeyCode has no character when the key does
    not produce one, so fall back to the virtual key code.

    The compactor relies on this: a name of length one means the key produced
    a character, which is how typing is told apart from shortcuts.
    """
    if isinstance(key, keyboard.Key):
        return key.name

    if key.char is not None:
        # ctrl turns a letter into a control character, so ctrl+c arrives as
        # \x03. the letter is what was actually pressed, so put it back
        if (ord(key.char) < 32) and key.vk:
            return chr(key.vk).lower()

        return key.char

    return "vk%s" % key.vk


def record(on_pause=None, on_ready=None) -> list:
    """
    Capture input until the stop key is pressed.

    Mouse and keyboard share one events list so the result is a single ordered
    timeline, which is far easier to compact and replay than two logs that have
    to be interleaved afterwards.
    """
    events = []
    held_keys = set()
    held_buttons = set()
    position = {"x": 0, "y": 0}
    start = time.perf_counter()

    # Paused time is subtracted from every timestamp, so a break in the middle
    # of recording closes up rather than becoming a long wait on replay
    pause = {"active": False, "since": 0.0, "total": 0.0}

    def elapsed():
        return time.perf_counter() - start - pause["total"]

    def toggle_pause():
        if pause["active"]:
            pause["total"] += time.perf_counter() - pause["since"]
            pause["active"] = False
            print("resumed")
        else:
            pause["since"] = time.perf_counter()
            pause["active"] = True
            print("paused, press %s again to resume" % config.PAUSE_KEY)

        # lets a caller show the state somewhere, since the key is global and
        # whatever started the recording is usually out of the way by now
        if on_pause:
            on_pause(pause["active"])

    # Callbacks run on the windows hook thread, so they only ever append and
    # return. Anything slow in here lags the whole desktop, and if a callback
    # stays slow for long enough windows drops the hook without saying so
    def add(event_type, **fields):
        if pause["active"]:
            return

        events.append({"t": elapsed(), "type": event_type, **fields})

    def on_move(x, y):
        position.update(x=x, y=y)
        add("move", x=x, y=y)

    def on_scroll(x, y, dx, dy):
        position.update(x=x, y=y)
        add("scroll", x=x, y=y, dx=dx, dy=dy)

    def on_click(x, y, button, pressed):
        position.update(x=x, y=y)

        if pressed:
            held_buttons.add(button.name)
        else:
            held_buttons.discard(button.name)

        add("click", x=x, y=y, button=button.name, pressed=pressed)

    def on_press(key):
        # returning False stops the listener, which releases the join below.
        # returning before recording keeps the stop key out of the macro
        if key == STOP_KEY:
            return False

        if key == PAUSE_KEY:
            toggle_pause()
            return

        name = key_to_str(key)

        # windows repeats a key that is being held. replaying the hold makes
        # the target repeat it again, so recording the repeats would double them
        if name in held_keys:
            return

        held_keys.add(name)
        add("key", key=name, pressed=True)

    def on_release(key):
        # the pause key's press was swallowed, so drop its release too
        if key == PAUSE_KEY:
            return

        name = key_to_str(key)
        held_keys.discard(name)
        add("key", key=name, pressed=False)

    mouse_listener = mouse.Listener(on_move=on_move,
                                    on_scroll=on_scroll,
                                    on_click=on_click)
    
    keyboard_listener = keyboard.Listener(on_press=on_press,
                                          on_release=on_release)

    print("recording, press %s to pause and %s to stop" % (config.PAUSE_KEY, config.STOP_KEY))
    mouse_listener.start()
    keyboard_listener.start()

    # hand the caller a way to stop us, since the stop key is not the only way
    # somebody might want to finish. stopping the listener releases the join
    if on_ready:
        on_ready(keyboard_listener.stop)

    keyboard_listener.join()
    mouse_listener.stop()
    mouse_listener.join()

    release_held(events, held_keys, held_buttons, position, elapsed())
    return events


def release_held(events: list, held_keys: set, held_buttons: set,
                 position: dict, t: float):
    """
    Close anything still down when recording stopped.

    An unmatched press compacts into a key_down or mouse_down with no partner,
    and the replayer would then hold that key for the rest of the run and leave
    it stuck afterwards.
    """
    for key in sorted(held_keys):
        events.append({"t": t, "type": "key", "key": key, "pressed": False})

    for button in sorted(held_buttons):
        events.append({"t": t, "type": "click", "button": button, "pressed": False,
                       "x": position["x"], "y": position["y"]})

    if held_keys or held_buttons:
        print("released %s input(s) still held at stop: %s"
              % (len(held_keys) + len(held_buttons),
                 ", ".join(sorted(held_keys | held_buttons))))


def save(events: list, path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w") as f:
        json.dump({"version": 1, "events": events}, f, indent=2)

    print("saved %s events to %s" % (len(events), path))


def main():
    enable_dpi_awareness()
    save(record(), config.RECORDING_PATH)


if __name__ == "__main__":
    main()
