import contextlib
import ctypes
import sys


def enable_dpi_awareness():
    """
    Ask windows for real pixel coordinates.

    Without this the cursor position is reported in scaled coordinates on a
    display that is not at 100%, so recording and replay quietly disagree about 
    where things are. It has to happen before anything reads a coordinate.
    """
    if sys.platform != "win32":
        return

    try:
        # -4 is DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2. it is a pointer
        # sized handle, so wrap it or ctypes passes a 32 bit int and the call
        # quietly does nothing
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        # older windows without the v2 context, system wide is better than none
        ctypes.windll.user32.SetProcessDPIAware()


@contextlib.contextmanager
def high_resolution_timer():
    """
    Ask windows for 1ms timer resolution for the duration of the block.

    By default sleep() rounds up to around 15.6ms, which is longer than the gap
    between recorded mouse positions, so a replay would run slow and jerky.
    """
    if sys.platform != "win32":
        yield
        return

    ctypes.windll.winmm.timeBeginPeriod(1)
    try:
        yield
    finally:
        ctypes.windll.winmm.timeEndPeriod(1)
