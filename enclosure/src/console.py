"""The pedal in its current case: a Hammond 1456RH3 sloped console carrying the Prechen 8.8"
bar screen (D14). Every dimension and position the console model uses, in one place.

This is the *new* model, beside the old 1590DD one (`layout.py`). It is a design render, not a
drilling template: the case and screen dimensions are the makers' drawings, but **every panel
position below is provisional**, read off the owner's chalk marks on the case
(`imaginings/big-enclosure/panel-sketch/`) by eye from photographs. The panel layout is not
designed yet. Do not drill from this file.

Plain Python with no imports, so any interpreter can read it.

Units are millimetres. The origin is the outside bottom-left-front corner of the closed case:
x runs left to right across the 434.82 mm width as the player sees it, y from the low front
edge (y = 0, nearest the player) to the tall rear wall, z up from the underside of the base.
"""
import math

# ---- The case: Hammond 1456RH3 (drawing 2720683, imaginings/big-enclosure/enclosure/) -------
# Two pieces of 12-gauge (2.06 mm) aluminium, both black for the BKBK part:
#   the case  -- the base and the two end panels, one U-shaped piece, the full footprint;
#   the cover -- front wall, 15 degree slope, flat top and rear wall, one wrap that sits between
#                the end panels (430.21 inside 430.71), screwed up through the base into
#                flanges along its front and rear feet.
W, D, H = 434.82, 218.67, 81.43   # outside
T = 2.06                          # sheet thickness
H_FRONT = 40.63                   # front wall's outside height
SLOPE = 15.0                      # degrees
COVER_W = 430.21                  # the cover's width, between the end panels
FLANGE_W = 418.78                 # the cover's foot flanges (the drawing's "top panel")
FLANGE_D = 13.0                   # how far each flange reaches in (not on the drawing: a guess)
R_BEND = 3.0                      # outside bend radius on the cover (not on the drawing)

# The slope: from the top of the front wall up at SLOPE degrees until it meets the flat top.
_rise = H - H_FRONT
SLOPE_RUN = _rise / math.tan(math.radians(SLOPE))    # 152.3 mm in plan
SLOPE_LEN = _rise / math.sin(math.radians(SLOPE))    # 157.6 mm along the face
Y_TOP = SLOPE_RUN                                    # where the flat top starts

# Six cover screws, up through the base: 409.55 x 204.77 mm centres, clearance holes 4.34 mm.
SCREW_D = 4.34
SCREWS = [(W / 2 + dx, D / 2 + dy) for dx in (-409.55 / 2, 0.0, 409.55 / 2) for dy in (-204.77 / 2, 204.77 / 2)]

# Four self-adhesive rubber feet (Hammond 1421T3, 0.5 x 0.5 in) near the corners.
FOOT_D, FOOT_H = 12.7, 5.5
FEET = [(x, y) for x in (22.0, W - 22.0) for y in (20.0, D - 20.0)]

# Vent slots, 3.18 x 22.23 mm with round ends: a band across the top of the rear wall
# (section A-A) and two groups through the base near the rear (bottom view).
SLOT_W, SLOT_L = 3.18, 22.23
REAR_SLOTS = dict(n=44, pitch=9.525, z0=53.2)                  # band z 53.2 to 75.4
BASE_SLOTS = dict(pitch=6.35, y0=D - 25.4 - SLOT_L, groups=((24.0, 166.0), (W - 166.0, W - 24.0)))

# ---- The screen: Prechen 8.8" IPS touch bar, 1920 x 480 (imaginings/big-enclosure/screen/) ---
SCREEN = dict(
    w=236.5, h=68.5, d=18.7,       # its own metal case
    active=(216.8, 54.2),          # 8.8" at 4:1
    mounts=(75.0, 50.0),           # M4 on the back; screws no more than 3 mm inside the case
    window=(229.0, 62.0, 2.5),     # the hole in the slope (w, h, corner radius): provisional
)

# ---- The sloped face (provisional) -----------------------------------------------------------
# Positions on the slope are (x, s): s is the distance up the face from its front edge, so a
# part at s sits at y = s cos 15, z = H_FRONT + s sin 15 on the outside surface.
CX = W / 2
SCREEN_S = 108.0                                # the screen's centre, up the face
FOOTSWITCH_S = 36.0                             # the row of five, nearest the player
FOOTSWITCH_PITCH = 80.0
FOOTSWITCHES = [(CX + k * FOOTSWITCH_PITCH, FOOTSWITCH_S, str(k + 3)) for k in range(-2, 3)]
TUNER = (CX - 159.0, 112.0)                     # the sixth: mute / tuner, left of the screen
VOLUME = (CX + 161.0, 125.0)                    # OUT VOLUME, a pot with a big knob
ENCODER = (CX + 150.0, 97.0)                    # the main rotary (an encoder with push)
APPLY = (CX + 172.0, 98.0)                      # the two small buttons beside it
BACK = (CX + 169.0, 86.0)

# ---- The rear wall (provisional) ---------------------------------------------------------------
# What the owner chalked on the rear wall, read from the photo, at x as the player sees it
# (from behind, the chalk runs the other way). z is the centre height. EXP is not chalked: it is
# here because the BOM lists an expression jack, and plan.md's debt table still asks whether the
# pedal needs one.
REAR_Z = 32.0
REAR = [
    # (key, kind, x, label)
    ("POWER", "rocker", 36.0, "Power"),
    ("USBC", "usbc", 62.0, "USB-C 5 V"),
    ("DC9V", "dc", 87.0, "9 V"),
    ("BATT", "battery", 117.0, "Battery"),
    ("EXP", "jack", 150.0, "Expression"),
    ("RF", "rfwindow", 181.0, "Wi-Fi / BT window"),
    ("MIDI_THRU", "din", 214.0, "MIDI thru"),
    ("MIDI_IN", "din", 240.0, "MIDI in"),
    ("OUT_L", "jack", 273.0, "Out L"),
    ("OUT_R", "jack", 307.0, "Out R"),
    ("LINE_IN", "jack", 339.0, "Line in"),
    ("MIC_IN", "combo", 367.0, "Mic in"),
    ("GUITAR_IN", "jack", 401.0, "Guitar in (Input 1)"),
]

# ---- Inside (provisional) ----------------------------------------------------------------------
# Boards on nylon standoffs on the base, (x0, y0) their front-left corner in plan, rot the turn
# in degrees. The stripboards are stripboard/module_boards.py's own layouts, sizes in holes.
STANDOFF = 8.0                    # mm from the base's top to a board's underside
P = 2.54
BOARDS = {
    # key in module_boards       x0      y0     rot
    "input-buffer":            (288.0, 150.0, 0),
    "output-l":                (252.0, 100.0, 0),
    "output-r":                (306.0, 100.0, 0),
    "power-9v":                (36.0, 150.0, 0),
}
PI5 = (100.0, 122.0)              # Raspberry Pi 5, 85 x 56 mm, front-left corner in plan
CODEC = (214.0, 92.0)             # SparkFun WM8960 breakout, 25.4 x 40.64 mm
PICO = (40.0, 96.0)               # Raspberry Pi Pico 2, 51 x 21 mm


def slope_point(x, s, out=0.0):
    """The point on the outside of the slope at (x, s), lifted `out` mm along its normal."""
    a = math.radians(SLOPE)
    return (x, s * math.cos(a) - out * math.sin(a), H_FRONT + s * math.sin(a) + out * math.cos(a))
