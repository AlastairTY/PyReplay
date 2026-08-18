from pynput import keyboard, mouse
from system import high_resolution_timer
import config
import time


ABORT_KEY = keyboard.Key[config.ABORT_KEY.lower()]
MOVE_INTERVAL = config.MOVE_INTERVAL_MS / 1000


def str_to_key(name: str):
    """Inverse of the recorder's key_to_str."""
    if name in keyboard.Key.__members__:
        return keyboard.Key[name]

    if name.startswith("vk"):
        return keyboard.KeyCode.from_vk(int(name[2:]))

    return keyboard.KeyCode.from_char(name)


class Player:
    """
    Walks a step list and performs it.

    The steps carry their own timing, since waits are explicit steps and a move
    carries the timestamps of its path, so there is no global schedule to keep.
    Each step simply takes as long as it takes.
    """

    def __init__(self, speed: float = None):
        self.speed = speed or config.PLAYBACK_SPEED
        self.aborted = False
        self.held_keys = set()
        self.held_buttons = set()
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()

    def run(self, steps: list) -> bool:
        """Perform every step, returning False if the run was aborted."""
        # the only listener running during playback, so nothing can feed our
        # own injected input back into a recording
        listener = keyboard.Listener(on_press=self.on_abort_key)
        listener.start()

        try:
            with high_resolution_timer():
                for step in steps:
                    if self.aborted:
                        break
                    self.play(step)
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

    def sleep_until(self, deadline: float):
        """Wait in slices so the abort key stays responsive during long waits."""
        while not self.aborted:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.02))

    def play(self, step: dict):
        handler = getattr(self, "play_" + step["type"], None)
        if handler is None:
            print("skipping unknown step type: %s" % step["type"])
            return

        handler(step)

    ### Movement
    def move_to(self, x: int, y: int):
        """
        Helper to move a cursor to an action's location.

        Travel to a point rather than jumping to it.
        """
        origin = self.mouse.position
        if origin == (x, y):
            return

        duration = (config.MOVE_DURATION_MS / 1000) / self.speed
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

        start = time.perf_counter()
        previous = path[0]
        self.mouse.position = (previous[1], previous[2])

        for point in path[1:]:
            if self.aborted:
                return

            span = point[0] - previous[0]
            slices = max(1, round(span / MOVE_INTERVAL))

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

    def play_click(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

        self.mouse.press(button)
        self.sleep_until(time.perf_counter() + (step.get("hold_ms", 50) / 1000) / self.speed)
        self.mouse.release(button)

    def play_mouse_down(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

        self.held_buttons.add(button)
        self.mouse.press(button)

    def play_mouse_up(self, step: dict):
        self.move_to(step["x"], step["y"])
        button = mouse.Button[step["button"]]

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
        delay = (step.get("delay_ms", config.TYPING_DELAY_MS) / 1000) / self.speed

        for n, character in enumerate(text):
            if self.aborted:
                return

            self.keyboard.type(character)
            if n < len(text) - 1:
                self.sleep_until(time.perf_counter() + delay)

    def play_key_press(self, step: dict):
        key = str_to_key(step["key"])
        self.keyboard.press(key)
        self.keyboard.release(key)

    def play_key_down(self, step: dict):
        key = str_to_key(step["key"])
        self.held_keys.add(key)
        self.keyboard.press(key)

    def play_key_up(self, step: dict):
        key = str_to_key(step["key"])
        self.keyboard.release(key)
        self.held_keys.discard(key)

    ### Timing

    def play_wait(self, step: dict):
        self.sleep_until(time.perf_counter() + (step["ms"] / 1000) / self.speed)


def play(steps: list, speed: float = None) -> bool:
    return Player(speed).run(steps)
