### Recorder
STOP_KEY = "F9"
PAUSE_KEY = "F10"
RECORDING_PATH = "outputs/recording.json"
MACRO_PATH = "outputs/macro.json"

### Editor
MACROS_DIR = "macros"
UNDO_DEPTH = 50

### Player
ABORT_KEY = "F9"
PLAYBACK_SPEED = 1.0
COUNTDOWN_SECONDS = 3
MOVE_DURATION_MS = 150     # how long to travel to a point with no recorded path
MOVE_INTERVAL_MS = 12      # gap between cursor updates while travelling

### Compactor
DRAG_THRESHOLD_PX = 5
CLICK_MAX_HOLD_MS = 300
TYPING_GAP_MS = 500
TYPING_MIN_RUN = 1
PATH_EPSILON = 2.0
SCROLL_GAP_MS = 200
WAIT_THRESHOLD_MS = 100
TYPING_DELAY_MS = 40       # per character, for steps written by hand
MAX_WAIT_MS = 5000
