import config
import math


def distance(a: dict, b: dict) -> float:
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def sign(n) -> int:
    return (n > 0) - (n < 0)


def perpendicular_distance(point: list, start: list, end: list) -> float:
    """How far a [t, x, y] point sits off the straight line from start to end."""
    _, px, py = point
    _, sx, sy = start
    _, ex, ey = end

    dx, dy = ex - sx, ey - sy
    if (dx == 0) and (dy == 0):
        return math.hypot(px - sx, py - sy)

    return abs(dx * (sy - py) - (sx - px) * dy) / math.hypot(dx, dy)


def simplify(points: list, epsilon: float) -> list:
    """
    Thin a path down to the points that describe its shape.

    Ramer-Douglas-Peucker: keep the point furthest from the straight line
    between the ends, and if even that is within epsilon then the straight
    line already describes the whole run.
    """
    if len(points) < 3:
        return points

    furthest, index = 0.0, 0
    for k in range(1, len(points) - 1):
        off = perpendicular_distance(points[k], points[0], points[-1])
        if off > furthest:
            furthest, index = off, k

    if furthest <= epsilon:
        return [points[0], points[-1]]

    # a real corner, so keep it and recurse either side, dropping the join
    # that both halves would otherwise report
    left = simplify(points[:index + 1], epsilon)
    right = simplify(points[index:], epsilon)
    return left[:-1] + right


def match_click(events: list, i: int) -> tuple | None:
    """
    To detect a typical fast mouse click. Drags and click & holds are
    ignored based on a default threshold for click hold and drag distance.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about click | None
    """
    press = events[i]

    # Not a press event, skip
    if (press["type"] != "click") or (not press["pressed"]):
        return None

    # Find the release that closes this press
    release = None
    for j in range(i + 1, len(events)):
        event = events[j]

        # moves inside the press window are hand jitter, skip over them
        if event["type"] == "move":
            continue

        # anything other than our own release means this press is not a click,
        # so leave the whole thing to the mouse fallback
        if not (event["type"] == "click" and event["button"] == press["button"] and not event["pressed"]):
            return None

        release = event
        break

    if release is None:
        return None

    # Detect whether it strayed too far or held too long to be a click
    if distance(press, release) > config.DRAG_THRESHOLD_PX:
        return None

    hold_ms = round((release["t"] - press["t"]) * 1000)
    if hold_ms > config.CLICK_MAX_HOLD_MS:
        return None

    step = {
        "type": "click",
        "x": press["x"],
        "y": press["y"],
        "button": press["button"],
        "hold_ms": hold_ms,
        "t_start": press["t"],
        "t_end": release["t"],
    }
    return step, j - i + 1


def match_mouse(events: list, i: int) -> tuple | None:
    """
    Fallback for any click the click matcher rejected, so drags and held
    buttons survive as an explicit down and up pair.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about the button change | None
    """
    event = events[i]
    if event["type"] != "click":
        return None

    step = {
        "type": "mouse_down" if event["pressed"] else "mouse_up",
        "x": event["x"],
        "y": event["y"],
        "button": event["button"],
        "t_start": event["t"],
        "t_end": event["t"],
    }
    return step, 1


def match_scroll(events: list, i: int) -> tuple | None:
    """
    To collect a burst of wheel notches into one scroll step, since a single
    flick of the wheel arrives as a handful of separate events.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about the scroll | None
    """
    first = events[i]
    if first["type"] != "scroll":
        return None

    direction = (sign(first["dx"]), sign(first["dy"]))
    dx, dy = 0, 0
    last_t = first["t"]

    j = i
    while j < len(events):
        event = events[j]
        if event["type"] != "scroll":
            break

        # scrolling back the other way is a new gesture, not more of this one
        if (sign(event["dx"]), sign(event["dy"])) != direction:
            break

        # so is picking the wheel up and flicking it again
        if ((event["t"] - last_t) * 1000) > config.SCROLL_GAP_MS:
            break

        dx += event["dx"]
        dy += event["dy"]
        last_t = event["t"]
        j += 1

    step = {
        "type": "scroll",
        "x": first["x"],
        "y": first["y"],
        "dx": dx,
        "dy": dy,
        "t_start": first["t"],
        "t_end": last_t,
    }
    return step, j - i


def match_move(events: list, i: int) -> tuple | None:
    """
    To collapse a run of raw mouse movement into a single travelled step,
    keeping the shape of the movement rather than just where it ended up.

    Args:
        events (list): recorded events list
        i (int): index start

    Returns:
        tuple | None: step information about the movement | None
    """
    if events[i]["type"] != "move":
        return None

    # Take every move up to the next event of any other kind
    j = i
    while (j < len(events)) and (events[j]["type"] == "move"):
        j += 1

    run = events[i:j]
    start, finish = run[0], run[-1]

    # Times are relative to the start of the run so the step stays self
    # contained if it gets moved around in the editor
    points = [[event["t"] - start["t"], event["x"], event["y"]] for event in run]

    step = {
        "type": "move",
        "from": [start["x"], start["y"]],
        "to": [finish["x"], finish["y"]],
        "path": simplify(points, config.PATH_EPSILON),
        "t_start": start["t"],
        "t_end": finish["t"],
    }
    return step, j - i
