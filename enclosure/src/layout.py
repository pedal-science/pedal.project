"""Where everything sits in the pedal. Shared by make_parts.py (KiCad's Python) and
build_scene.py (Blender's Python), so it must stay plain Python with no imports.

Units are millimetres in enclosure coordinates: the origin is the outside bottom-left-front
corner of the closed box, x runs left to right across the 145.2 mm face, y runs from the
player's edge (front, y = 0) to the jack edge (rear), and z runs up from the base plate.
"""

P = 2.54  # stripboard and header pitch

# Hammond 1590XX (drawing 1590XX, dimensions at the open rim).
ENC = dict(
    W=145.2, D=121.2, H=39.3,   # outside, with the lid fitted
    lid=1.5,                    # base plate thickness; its lip rises lid_lip above it
    lid_lip=2.6, lip_w=1.6,
    wall=2.3,                   # side walls
    top=2.6,                    # top face (the casting's floor)
    r_corner=6.0,               # vertical outside corners
    r_top=3.0,                  # fillet between the top face and the walls
    draft=0.6,                  # each wall leans in by this much from rim to top
    boss_d=8.2,                 # lid-screw bosses in the inside corners
    screw_dx=135.0, screw_dy=111.0,
)
Z_LID_TOP = ENC["lid"]                        # 1.5
Z_TOP_IN = ENC["H"] - ENC["top"]              # 36.7, underside of the top face
CX, CY = ENC["W"] / 2, ENC["D"] / 2

# ---- Top face -----------------------------------------------------------------------------
STRIPE_Y = (53.0, 107.0)                      # orange band across the top and down the sides

FS_X = [CX - 52.0, CX, CX + 52.0]             # three footswitches, 52 mm apart
FS_Y = 24.0
LED_Y = 42.0                                  # a status LED above each footswitch
LED_READY = (12.5, 80.0)                      # fourth LED, left end of the stripe
TOGGLE = (131.0, 80.0)                        # Inst / Line, right end of the stripe

# Display module (2.4" ST7789 + EC11 + tact switch, board V1.2): 90 x 43.2 mm. Offsets are
# from the board's top-left corner as photographed (header on the left edge), and the
# photo's top edge faces the rear of the pedal.
DISP = dict(w=90.0, h=43.2,
            screen_c=(34.2, 21.8), active=(48.96, 36.72), glass=(60.4, 42.7), glass_x0=6.7,
            enc=(80.8, 12.0), btn=(79.1, 31.2),
            pads_x=2.8, pads_y0=7.7, holes=[(2.7, 3.0), (87.4, 3.0), (2.7, 40.2), (87.4, 40.2)])
DISP_X0 = 24.7                                # left edge, centres the screen + controls
DISP_YTOP = 101.6                             # rear edge
DISP_PCB_TOP = Z_TOP_IN - 6.6                 # the EC11's body sets how far down it hangs


def disp_to_enc(u, v):
    """Display-board offsets (from its top-left, v down) to enclosure x, y."""
    return DISP_X0 + u, DISP_YTOP - v


WINDOW_C = disp_to_enc(*DISP["screen_c"])     # (58.9, 79.8)
WINDOW = (51.0, 38.6)
ENCODER = disp_to_enc(*DISP["enc"])           # (105.5, 89.6)
BUTTON = disp_to_enc(*DISP["btn"])            # (103.8, 70.4)

# ---- Walls --------------------------------------------------------------------------------
JACK_Z = 17.5
JACKS = {  # name: (wall, position along the wall, z)
    "OUT_R": ("left", 66.0, JACK_Z),
    "OUT_L": ("left", 97.0, JACK_Z),
    "EXP": ("right", 66.0, JACK_Z),
    "IN": ("right", 97.0, JACK_Z),
}
USBC = (44.0, 29.5)       # rear wall: x, z
DC9V = (76.0, 25.0)       # clears the Pico and the display board
MIDI = (108.0, 25.5)

# ---- Inside, on the base plate ------------------------------------------------------------
PI5_ORIGIN = (22.0, 6.0)      # PCB corner (the HDMI edge faces the front wall)
PI5_STANDOFF = 3.0            # M2.5 brass standoffs on the base plate
BOARD_STANDOFF = 5.0          # M3 standoffs under both stripboards
PCB_T = 1.6

# Stripboards (Kemo E005, FR4, strips run along x). Row 0 is the rear edge.
BOARD_B = dict(name="board_b", x0=27.0, y0=65.0, cols=16, rows=20)   # Pico, MIDI, relay
BOARD_A = dict(name="board_a", x0=72.0, y0=65.0, cols=18, rows=20)   # buffer, power, codec


def hole(board, col, row):
    """Enclosure x, y of a stripboard hole."""
    return (board["x0"] + P / 2 + col * P,
            board["y0"] + board["rows"] * P - P / 2 - row * P)


BOARD_Z = Z_LID_TOP + BOARD_STANDOFF          # underside of both stripboards
BOARD_TOP = BOARD_Z + PCB_T

SOCKET_H = 8.5                                # 2.54 mm socket strip height
HEADER_BASE = 2.5                             # plastic spacer of a pin header
