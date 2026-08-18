import config


# pynput reports left and right variants separately. shift and alt_gr are
# already baked into the recorded character ("H", not shift plus "h"), so a
# typing run can swallow them. ctrl/alt/cmd change what a key means, so they
# end a run instead
TRANSPARENT_MODIFIERS = {"shift", "shift_l", "shift_r", "alt_gr"}
BREAKING_MODIFIERS = {"ctrl", "ctrl_l", "ctrl_r",
                      "alt", "alt_l", "alt_r",
                      "cmd", "cmd_l", "cmd_r"}


def modifiers_held(events: list, i: int) -> set:
    """
    Which breaking modifiers are still down immediately before index i.

    Matchers only see events[i:], so a run of printable keys cannot otherwise
    tell whether it is text or the tail of a shortcut.
    """
    held = set()
    for event in events[:i]:
        if (event["type"] != "key") or (event["key"] not in BREAKING_MODIFIERS):
            continue

        if event["pressed"]:
            held.add(event["key"])
        else:
            held.discard(event["key"])

    return held


def match_typing(events: list, i: int) -> tuple | None:
    """
    To collapse a run of printable keystrokes into one editable block of text.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about the typed text | None
    """
    first = events[i]

    # A run starts on a printable key or on the shift
    if (first["type"] != "key") or (not first["pressed"]):
        return None

    if (len(first["key"]) != 1) and (first["key"] not in TRANSPARENT_MODIFIERS):
        return None

    # Ctrl/alt/cmd already down means this is a shortcut
    if modifiers_held(events, i):
        return None

    chars = []
    open_modifiers = set()
    first_char_t = None
    last_t = None

    # j is where we are looking, end is how far the run is confirmed to reach.
    # A swallowed shift only counts once a character follows it, otherwise the
    # run would eat the shift belonging to whatever comes next
    j = i
    end = i
    while j < len(events):
        event = events[j]
        if event["type"] != "key":
            break

        key = event["key"]

        if event["pressed"]:
            if key in TRANSPARENT_MODIFIERS:
                open_modifiers.add(key)
                j += 1
                continue    # deliberately not extending end

            # a non printable key ends the run and is left to match_key
            if len(key) != 1:
                break

            # a long pause is a separate run, so insert_waits can split them
            if (last_t is not None) and ((event["t"] - last_t) * 1000 > config.TYPING_GAP_MS):
                break

            chars.append(key)
            if first_char_t is None:
                first_char_t = event["t"]
            last_t = event["t"]
            j += 1
            end = j
            continue

        # Step over the releases of keys this run already took, since typing
        # reads as "h down, h up, e down" and would otherwise stop at the
        # first release. Any other release belongs to a key held from before
        # the run, so stop there and let match_key close it
        if (len(key) == 1) or (key in open_modifiers):
            open_modifiers.discard(key)
            j += 1
            end = j
            continue

        break

    if len(chars) < config.TYPING_MIN_RUN:
        return None

    # Spread the run's real duration over the characters, so replay types at
    # roughly the speed it was recorded instead of arriving all at once. Per
    # character rather than a total, so editing the text keeps the pace
    gaps = len(chars) - 1
    delay_ms = round((last_t - first_char_t) * 1000 / gaps) if gaps else config.TYPING_DELAY_MS

    step = {
        "type": "type_text",
        "text": "".join(chars),
        "delay_ms": delay_ms,
        "t_start": first["t"],
        "t_end": last_t,
    }
    return step, end - i


def match_key(events: list, i: int) -> tuple | None:
    """
    Fallback for any key the typing matcher did not take, such as enter, tab
    and the modifiers of a shortcut.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about the key | None
    """
    event = events[i]
    if event["type"] != "key":
        return None

    # A release whose press went into a typing run, or a key held from before.
    # Releasing a key that is not down is a no-op, so emitting this is safe
    if not event["pressed"]:
        step = {
            "type": "key_up",
            "key": event["key"],
            "t_start": event["t"],
            "t_end": event["t"],
        }
        return step, 1

    # A press immediately closed by its own release is one self contained tap
    if i + 1 < len(events):
        following = events[i + 1]
        if ((following["type"] == "key") and (following["key"] == event["key"]) and (not following["pressed"])):
            step = {
                "type": "key_press",
                "key": event["key"],
                "t_start": event["t"],
                "t_end": following["t"],
            }
            return step, 2

    # Still held while something else happens. Leaving it open is what makes
    # ctrl+c and shift+tab replay correctly without a dedicated hotkey matcher
    step = {
        "type": "key_down",
        "key": event["key"],
        "t_start": event["t"],
        "t_end": event["t"],
    }
    return step, 1
