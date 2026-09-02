from pynput import keyboard, mouse
from system import high_resolution_timer
import config
import math
import time


ABORT_KEY = keyboard.Key[config.ABORT_KEY.lower()]
MOVE_INTERVAL = config.MOVE_INTERVAL_MS / 1000


def str_to_key(name: str):
    """Inverse of the recorder's key_to_str."""
    if name in keyboard.Key.__members__:
        return keyboard.Key[name]

    if name.startswith("vk"):
        return keyboard.KeyCode.from_vk(int(name[2:]))

    # older recordings stored ctrl+c as \x03, which no key produces on its own.
    # send the letter and let the held ctrl do its work
    if (len(name) == 1) and (ord(name) < 32):
        return keyboard.KeyCode.from_char(chr(ord(name) + 96))

    return keyboard.KeyCode.from_char(name)


class Player:
    """
    Walks a step list and performs it.

    The steps carry their own timing, since waits are explicit steps and a move
    carries the timestamps of its path, so there is no global schedule to keep.
    Each step simply takes as long as it takes.
    """

    def __init__(self, speed: float = None, on_step=None):
        self.speed = speed or config.PLAYBACK_SPEED
        # called with the index of each step as it starts, so a caller running
        # this on a worker thread can follow along
        self.on_step = on_step
        self.aborted = False
        self.held_keys = set()
        self.held_buttons = set()
        self.holding = {}
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()

    def run(self, steps: list, start: int = 0) -> bool:
        """Perform every step from start onwards, returning False if aborted."""
        # the only listener running during playback, so nothing can feed our
        # own injected input back into a recording
        listener = keyboard.Listener(on_press=self.on_abort_key)
        listener.start()

        try:
            with high_resolution_timer():
                for index in range(start, len(steps)):
                    if self.aborted:
                        break

                    if self.on_step:
                        self.on_step(index)

                    self.play(steps[index])
        finally:
            self.release_held()
            listener.stop()

        return not self.aborted

    def on_abort_key(self, key):
        if key == ABORT_KEY:
            self.aborted = True
            return False

    def release_held(self):
        """
        Let go of anything this run is still holding.

        Without this an abort partway through a shortcut, or a macro whose
        key_down never got a key_up, leaves a modifier stuck down system wide
        long after the run has finished.
        """
        for key in self.held_keys:
            self.keyboard.release(key)

        for button in self.held_buttons:
            self.mouse.release(button)

        if self.held_keys or self.held_buttons:
            print("released %s input(s) still held" %
                  (len(self.held_keys) + len(self.held_buttons)))

        self.held_keys.clear()
        self.held_buttons.clear()
        self.holding.clear()

    def sleep_until(self, deadline: float):
        """Wait in slices so the abort key stays responsive during long waits."""
        while not self.aborted:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.02))

    def play(self, step: dict):
        # missing means enabled, so nothing has to write the field until a step
        # is actually switched off
        if not step.get("enabled", True):
            return

        handler = getattr(self, "play_" + step["type"], None)
        if handler is None:
            print("skipping unknown step type: %s" % step["type"])
            return

        handler(step)

    ### Movement
    def move_to(self, x: int, y: int):
        """
        Helper to move a cursor to an action's location.

        Travels there rather than jumping, unless config says to jump. Some
        applications need the motion in between to fire hover states or to
        recognise a drag, and others only care where the cursor ends up.
        """
        origin = self.mouse.position
        travel = math.hypot(x - origin[0], y - origin[1])
        if travel < 1:
            return

        if not config.SMOOTH_TRAVEL:
            self.mouse.position = (x, y)
            return

        # proportional to the distance and capped, so correcting a pixel of
        # drift does not take as long as crossing the screen
        seconds = min(travel / config.MOVE_SPEED_PX, config.MOVE_DURATION_MS / 1000)
        duration = seconds / self.speed
        slices = max(1, round(duration / MOVE_INTERVAL))
        start = time.perf_counter()

        for n in range(1, slices + 1):
            if self.aborted:
                return

            fraction = n / slices
            self.mouse.position = (round(origin[0] + (x - origin[0]) * fraction),
                                   round(origin[1] + (y - origin[1]) * fraction))
            self.sleep_until(start + duration * fraction)

    def play_move(self, step: dict):
        """
        Retrace a recorded route one segment at a time

        The stored path only holds the points that survived thinning, so the
        positions between them are generated again here. Each segment is timed
        from the points themselves, which is what makes the replay move slowly
        where the hand moved slowly and quickly where it flicked.
        """

        path = step.get("path") or []

        # a path was thinned down to the points that describe its shape, so fill
        # the gaps back in rather than jumping between them
        if len(path) < 2:
            self.move_to(*step["to"])
            return

        # travel to the start rather than jumping, in case a step was reordered
        # and the cursor is no longer where the path begins
        previous = path[0]
        self.move_to(previous[1], previous[2])

        start = time.perf_counter()
        for point in path[1:]:
            if self.aborted:
                return

            # scaled by speed, or a fast replay issues the same number of
            # cursor updates in a fraction of the time and floods the queue
            span = point[0] - previous[0]
            slices = max(1, round((span / self.speed) / MOVE_INTERVAL))

            for n in range(1, slices + 1):
                fraction = n / slices
                self.mouse.position = (
                    round(previous[1] + (point[1] - previous[1]) * fraction),
                    round(previous[2] + (point[2] - previous[2]) * fraction),
                )
                # scheduled against the path's own start so the error does not
                # build up across a long path
                self.sleep_until(start + (previous[0] + span * fraction) / self.speed)

            previous = point

    ### Mouse buttons

    def hold(self, ms: float, since: float = None):
        """
        Wait until something has been down for ms.

        An application that samples input periodically, rather than reading
        every event, cannot see a press and release in the same instant. When
        since is given the wait covers whatever already happened, so a button
        held across other steps still ends up down for as long as it was.
        """
        started = time.perf_counter() if since is None else since
        self.sleep_until(started + (ms / 1000) / self.speed)

    def top_up(self, kind: str, name: str):
        """
        Wait out the rest of a hold before releasing.

        The steps in between may not take as long as they did when recorded,
        which would let go early and cut the action short.
        """
        pressed, hold_ms = self.holding.pop((kind, name), (None, None))
        if hold_ms:
            self.hold(hold_ms, since=pressed)

    def play_click(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

        self.mouse.press(button)
        self.hold(step.get("hold_ms", config.HOLD_MS))
        self.mouse.release(button)

    def play_mouse_down(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

        self.held_buttons.add(button)
        self.holding["button", step["button"]] = (time.perf_counter(), step.get("hold_ms"))
        self.mouse.press(button)

    def play_mouse_up(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

        self.top_up("button", step["button"])
        self.mouse.release(button)
        self.held_buttons.discard(button)

    def play_scroll(self, step: dict):
        self.move_to(step["x"], step["y"])
        self.mouse.scroll(step["dx"], step["dy"])

    ### Keyboard

    def play_type_text(self, step: dict):
        # typed one character at a time, since Controller.type() sends the whole
        # string as fast as it can and outruns anything that validates as you go
        text = step["text"]
        delay_ms = step.get("delay_ms", config.TYPING_DELAY_MS)

        # each key is held for as long as it was, and the hold comes out of
        # the gap to the next one so the run keeps its pace
        hold_ms = step.get("hold_ms", min(config.HOLD_MS, delay_ms))

        for n, character in enumerate(text):
            if self.aborted:
                return

            self.keyboard.press(character)
            self.hold(hold_ms)
            self.keyboard.release(character)

            if n < len(text) - 1:
                self.hold(max(0, delay_ms - hold_ms))

    def play_key_press(self, step: dict):
        key = str_to_key(step["key"])
        self.keyboard.press(key)
        self.hold(step.get("hold_ms", config.HOLD_MS))
        self.keyboard.release(key)

    def play_key_down(self, step: dict):
        key = str_to_key(step["key"])
        self.held_keys.add(key)
        self.holding["key", step["key"]] = (time.perf_counter(), step.get("hold_ms"))
        self.keyboard.press(key)

    def play_key_up(self, step: dict):
        self.top_up("key", step["key"])

        key = str_to_key(step["key"])
        self.keyboard.release(key)
        self.held_keys.discard(key)

    ### Timing

    def play_wait(self, step: dict):
        self.hold(step["ms"])


def play(steps: list, speed: float = None) -> bool:
    return Player(speed).run(steps)
