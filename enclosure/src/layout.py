"""Where everything sits in the pedal. Shared by make_parts.py (KiCad's Python) and
build_scene.py (Blender's Python), so it must stay plain Python with no imports.

Units are millimetres in enclosure coordinates: the origin is the outside bottom-left-front
corner of the closed box, x runs left to right across the 188 mm face, y runs from the
player's edge (front, y = 0) to the jack edge (rear), and z runs up from the base plate.
"""

P = 2.54  # stripboard and header pitch

# A 1590DD-size box, 188 x 119 x 37.5 mm (the 33 mm-high Tayda one was too tight for the
# Pi's Dupont leads under the display and for the DIN socket).
ENC = dict(
    W=188.0, D=119.0, H=37.5,   # outside, with the lid fitted
    lid=1.5,                    # base plate thickness; its lip rises lid_lip above it
    lid_lip=2.6, lip_w=1.6,
    wall=3.0,                   # side walls
    top=2.6,                    # top face (the casting's floor)
    r_corner=6.0,               # vertical outside corners
    r_top=3.0,                  # fillet between the top face and the walls
    draft=0.6,                  # each wall leans in by this much from rim to top
    boss_d=8.2,                 # lid-screw bosses in the inside corners
    screw_dx=173.8, screw_dy=104.8,
)
Z_LID_TOP = ENC["lid"]                        # 1.5
Z_TOP_IN = ENC["H"] - ENC["top"]              # 34.9, underside of the top face
CX, CY = ENC["W"] / 2, ENC["D"] / 2

# ---- Top face -----------------------------------------------------------------------------
STRIPE_Y = (53.0, 106.0)                      # orange band across the top and down the sides

FS_X = [CX - 69.0, CX, CX + 69.0]             # three footswitches, 69 mm apart
FS_Y = 24.0
LED_Y = 42.0                                  # a status LED above each footswitch
# Fourth LED and the Inst / Line toggle, at the ends of the stripe, level with the display's
# button. Both sit over the low parts of the stripboards under them.
LED_READY = (14.8, 70.0)
TOGGLE = (ENC["W"] - 14.8, 70.0)

# Display module (2.4" ST7789 + EC11 + tact switch, board V1.2): 90 x 43.2 mm. Offsets are
# from the board's top-left corner as photographed (header on the left edge), and the
# photo's top edge faces the rear of the pedal.
DISP = dict(w=90.0, h=43.2,
            screen_c=(34.2, 21.8), active=(48.96, 36.72), glass=(60.4, 42.7), glass_x0=6.7,
            enc=(80.8, 12.0), btn=(79.1, 31.2),
            pads_x=2.8, pads_y0=7.7, holes=[(2.7, 3.0), (87.4, 3.0), (2.7, 40.2), (87.4, 40.2)])
DISP_X0 = 46.1                                # left edge, centres the screen + controls
DISP_YTOP = 101.3                             # rear edge
DISP_PCB_TOP = Z_TOP_IN - 6.6                 # the EC11's body sets how far down it hangs


def disp_to_enc(u, v):
    """Display-board offsets (from its top-left, v down) to enclosure x, y."""
    return DISP_X0 + u, DISP_YTOP - v


WINDOW_C = disp_to_enc(*DISP["screen_c"])     # (80.3, 79.5)
WINDOW = (51.0, 38.6)
ENCODER = disp_to_enc(*DISP["enc"])           # (126.9, 89.3)
BUTTON = disp_to_enc(*DISP["btn"])            # (125.2, 70.1)

# ---- Rear wall ----------------------------------------------------------------------------
# Everything is on the rear: outputs at the left, inputs at the right (as the player sees
# it), and power and MIDI between. The outer jacks clear the lid-screw bosses.
REAR_Z = 16.0             # the DIN socket just clears the display board
JACKS = {  # name: (wall, position along the wall, z)
    "OUT_L": ("rear", 21.0, REAR_Z),
    "OUT_R": ("rear", 43.0, REAR_Z),
    "EXP": ("rear", 145.0, REAR_Z),
    "IN": ("rear", 167.0, REAR_Z),
}
USBC = (65.0, REAR_Z)     # rear wall: x, z
MIDI = (93.0, REAR_Z)
DC9V = (121.0, REAR_Z)
REAR_LABEL_Z = 29.5       # the printed names, in one row above the connectors

# ---- Inside, on the base plate ------------------------------------------------------------
PI5_ORIGIN = (47.0, 5.0)      # PCB corner (the HDMI edge faces the front wall)
PI5_STANDOFF = 3.0            # M2.5 brass standoffs on the base plate
BOARD_STANDOFF = 3.0          # M3 standoffs under both stripboards; 3 mm keeps the Pico under LED A
PCB_T = 1.6

# Stripboards (Kemo E005, FR4, strips run along x). Row 0 is the rear edge.
# Board B sits left of the Pi, under the display's leads; board A right of it, near the inputs.
BOARD_B = dict(name="board_b", x0=4.0, y0=42.2, cols=16, rows=20)    # Pico, MIDI, relay
BOARD_A = dict(name="board_a", x0=137.0, y0=41.5, cols=18, rows=20)  # buffer, power, codec


def hole(board, col, row):
    """Enclosure x, y of a stripboard hole."""
    return (board["x0"] + P / 2 + col * P,
            board["y0"] + board["rows"] * P - P / 2 - row * P)


BOARD_Z = Z_LID_TOP + BOARD_STANDOFF          # underside of both stripboards
BOARD_TOP = BOARD_Z + PCB_T

SOCKET_H = 8.5                                # 2.54 mm socket strip height
HEADER_BASE = 2.5                             # plastic spacer of a pin header
