import json
import os


def load(path: str, key: str = "steps") -> list:
    with open(path) as f:
        return json.load(f)[key]


def save(steps: list, path: str):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w") as f:
        json.dump({"version": 1, "steps": steps}, f, indent=2)


def summarise(step: dict) -> str:
    """One line describing a step, for the editor's list and the CLI."""
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