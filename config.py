### Recorder
STOP_KEY = "F9"
PAUSE_KEY = "F10"
RECORDING_PATH = "outputs/recording.json"
MACRO_PATH = "outputs/macro.json"

### Editor
APP_NAME = "PyReplay"
MACROS_DIR = "macros"
ASSETS_DIR = "assets"
LOGO = "pyreplay.png"
UNDO_DEPTH = 50

### Player
ABORT_KEY = "F9"
PLAYBACK_SPEED = 1.0
HOLD_MS = 50               # how long a key or button stays down, if unrecorded
COUNTDOWN_SECONDS = 3
MOVE_DURATION_MS = 150     # longest a travel to a point may take
MOVE_SPEED_PX = 3000       # travel speed, so short hops stay short
SMOOTH_TRAVEL = True       # False jumps to a point instead of travelling to it
MOVE_INTERVAL_MS = 12      # gap between cursor updates while travelling

### Compactor
DRAG_THRESHOLD_PX = 5
CLICK_MAX_HOLD_MS = 300
KEY_MAX_HOLD_MS = 300     # longer than this is a held key, not a keystroke
TYPING_GAP_MS = 500
TYPING_MIN_RUN = 1
PATH_EPSILON = 2.0
SCROLL_GAP_MS = 200
WAIT_THRESHOLD_MS = 100
TYPING_DELAY_MS = 40       # per character, for steps written by hand
MAX_WAIT_MS = 5000

### Overlay
OVERLAY_BORDER_PX = 5
