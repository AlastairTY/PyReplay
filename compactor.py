from key_compactor import match_key, match_typing
from mouse_compactor import match_click, match_mouse, match_move, match_scroll
import config


# Specific matchers go first, then go to fallbacks if needed
MATCHERS = [
    match_click,
    match_typing,
    match_key,
    match_mouse,
    match_scroll,
    match_move,
]


def scan(events: list) -> list:
    """Run the matchers over the raw events to produce steps."""
    steps = []
    i = 0
    while i < len(events):
        for matcher in MATCHERS:
            result = matcher(events, i)

            if result:
                step, consumed = result
                steps.append(step)
                i += consumed
                break
        else:
            # nothing claimed it
            i += 1

    return steps


def make_wait(gap_ms: int, t_start: float, t_end: float) -> dict:
    """
    A pause long enough to be worth showing as its own step.

    Very long gaps are capped, since a break for a phone call should not turn
    into a macro that sits doing nothing for four minutes. The note is there so
    the cap is visible rather than a silent decision made on the user's behalf.
    """
    wait = {
        "type": "wait",
        "ms": min(gap_ms, config.MAX_WAIT_MS),
        "t_start": t_start,
        "t_end": t_end,
    }

    if gap_ms > config.MAX_WAIT_MS:
        wait["note"] = "clamped from %.1fs" % (gap_ms / 1000)

    return wait


def insert_waits(steps: list) -> list:
    """
    Turn the gaps between steps into wait steps.

    The matchers consume events, so the time between what they produced only
    exists in the timestamps they carry. Making it a step is what lets the
    timing be seen and edited instead of being baked into the recording.
    """
    out = []

    # a gap too small to be worth a step is carried into the next one rather
    # than dropped. otherwise the lost milliseconds add up and a key held
    # across many steps comes out shorter than it was
    carried = 0.0

    for step in steps:
        if out:
            gap = (step["t_start"] - out[-1]["t_end"]) + carried
            gap_ms = round(gap * 1000)

            if gap_ms > config.WAIT_THRESHOLD_MS:
                out.append(make_wait(gap_ms, out[-1]["t_end"], step["t_start"]))
                carried = 0.0
            else:
                carried = gap

        out.append(step)

    return out


def compact(events: list) -> list:
    return insert_waits(scan(events))
