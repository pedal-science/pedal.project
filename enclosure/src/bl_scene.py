"""The set: wooden floor, standing lights, cameras and render settings. Metres."""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

import bl_util as U
from bl_parts import MB, lathe

TEX = os.path.join(U.ASSETS, "textures")


def floor(coll):
    me = bpy.data.meshes.new("Floor")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=4.0)
    bm.to_mesh(me)
    bm.free()
    o = U.new_obj("Floor", me, coll)
    m = bpy.data.materials.new("WoodFloor")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    n = U.node
    tc = n(nt, "ShaderNodeTexCoord", (-1400, 0))
    mp = n(nt, "ShaderNodeMapping", (-1200, 0))
    mp.inputs["Scale"].default_value = (1 / 1.7, 1 / 1.7, 1)
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(90))
    mp.inputs["Location"].default_value = (0.37, 0.11, 0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def tex(name, noncolor, loc):
        t = n(nt, "ShaderNodeTexImage", loc)
        t.image = bpy.data.images.load(os.path.join(TEX, f"wood_floor_{name}_4k.jpg"))
        if noncolor:
            t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t
    diff = tex("diff", False, (-900, 300))
    rough = tex("rough", True, (-900, 0))
    nor = tex("nor_gl", True, (-900, -300))
    hsv = n(nt, "ShaderNodeHueSaturation", (-600, 300))
    hsv.inputs["Saturation"].default_value = 1.05
    hsv.inputs["Value"].default_value = 0.72
    nt.links.new(diff.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], b.inputs["Base Color"])
    rr = n(nt, "ShaderNodeMapRange", (-600, 0))
    rr.inputs["To Min"].default_value = 0.22
    rr.inputs["To Max"].default_value = 0.62
    nt.links.new(rough.outputs["Color"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    nm = n(nt, "ShaderNodeNormalMap", (-600, -300))
    nm.inputs["Strength"].default_value = 1.0
    nt.links.new(nor.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.15
    b.inputs["Coat Roughness"].default_value = 0.15
    o.data.materials.append(m)
    return o


def emissive(name, rgb, strength):
    return U.principled(name, (0.02, 0.02, 0.02), rough=0.3, emission=rgb, emission_strength=strength)


def tube_light(coll, M, name, loc, rgb, strength=38.0, height=0.62, lean=0.0, turn=0.0):
    """A battery LED tube (like a Nanlite PavoTube) standing in a weighted round base."""
    mb = MB(name)
    r = 0.016
    alu = M.alu_dark
    mb.add(M.rubber, lambda bm: lathe(bm, [(0.0, 0.0), (0.058, 0.0), (0.06, 0.006), (0.055, 0.016), (0.02, 0.022),
                                           (0.0, 0.022)], seg=48))
    mb.add(alu, lambda bm: U.cyl(bm, 0.009, 0.02, 0.07, seg=24))
    mb.add(alu, lambda bm: U.cyl(bm, r + 0.002, 0.065, 0.1, seg=32))
    mb.add(emissive(name + "_glow", rgb, strength), lambda bm: U.cyl(bm, r, 0.1, height - 0.035, seg=32))
    mb.add(alu, lambda bm: U.cyl(bm, r + 0.002, height - 0.035, height, seg=32))
    mb.add(M.black_plastic, lambda bm: U.cyl(bm, 0.004, height, height + 0.004, seg=16))
    o = mb.obj(coll, bevel=0.0015, seg=2)
    o.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Rotation(lean, 4, "X")
    return o


def fresnel(coll, M, name, loc, aim, height=0.34, power=180.0, rgb=(1.0, 0.86, 0.7)):
    """A small Fresnel spot on a three-leg stand, with a real spot light in its lens."""
    loc, aim = Vector(loc), Vector(aim)
    head = loc + Vector((0, 0, height))
    d = (aim - head).normalized()
    mb = MB(name + "_stand")
    steel = M.black_oxide
    for k in range(3):
        a = math.radians(90 + 120 * k)
        foot = loc + Vector((math.cos(a), math.sin(a), 0)) * 0.13
        top = loc + Vector((0, 0, 0.11))

        def leg(bm, foot=foot, top=top):
            v = top - foot
            U.cyl(bm, 0.0045, 0, v.length, seg=12)
            bmesh.ops.transform(bm, matrix=Matrix.Translation(foot) @ v.to_track_quat("Z", "Y").to_matrix().to_4x4(),
                                verts=bm.verts)
        mb.add(steel, leg)
        mb.add(M.rubber, lambda bm, foot=foot: U.cyl(bm, 0.008, 0, 0.006, x=foot.x, y=foot.y, seg=16))
    mb.add(steel, lambda bm: U.cyl(bm, 0.009, 0.1, height - 0.02, x=loc.x, y=loc.y, seg=20))
    mb.add(steel, lambda bm: U.cyl(bm, 0.012, 0.1, 0.13, x=loc.x, y=loc.y, seg=20))
    mb.obj(coll, bevel=0.001, seg=1)
    # Head: yoke, finned body, lens, barn-door frame; built along +Z then aimed.
    hb = MB(name + "_head")
    body = M.lamp_paint
    hb.add(body, lambda bm: lathe(bm, [(0.0, -0.075), (0.05, -0.075), (0.056, -0.068), (0.056, 0.02), (0.061, 0.024),
                                       (0.061, 0.034), (0.052, 0.034), (0.052, 0.03), (0.0, 0.03)], seg=64))
    for i in range(9):
        z = -0.066 + i * 0.0085
        hb.add(M.lamp_fin, lambda bm, z=z: U.cyl(bm, 0.062, z, z + 0.0028, seg=64))
    hb.add(M.lens_glow, lambda bm: lathe(bm, [(0.0, 0.037), (0.02, 0.0365), (0.046, 0.034), (0.046, 0.03), (0.0, 0.03)],
                                         seg=64))
    for k in range(10):
        r0 = 0.012 + k * 0.0035

        def ring(bm, r0=r0):
            lathe(bm, [(r0, 0.0335), (r0 + 0.0028, 0.0335), (r0 + 0.003, 0.0352), (r0, 0.0352)], seg=48, closed=True)
        hb.add(M.lens_ring, ring)
    for sgn in (-1, 1):
        hb.add(body, lambda bm, s=sgn: U.box(bm, s * 0.068, -0.012, -0.03, s * 0.071, 0.012, 0.03))
        hb.add(body, lambda bm, s=sgn: U.cyl(bm, 0.009, s * 0.058 - 0.004, s * 0.058 + 0.004, seg=20,
                                             matrix=Matrix.Rotation(math.radians(90), 4, "Y")))
    for ang in (0, 90, 180, 270):
        def door(bm, ang=ang):
            U.box(bm, -0.05, 0.061, 0.034, 0.05, 0.063, 0.085)
            bmesh.ops.rotate(bm, cent=(0, 0.062, 0.034), matrix=Matrix.Rotation(math.radians(-28), 3, "X"),
                             verts=bm.verts)
            bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(ang), 3, "Z"), verts=bm.verts)
        hb.add(body, door)
    # Control panel on the back: a small lit display and two buttons.
    hb.add(M.panel_glow, lambda bm: U.box(bm, -0.018, -0.011, -0.0765, 0.018, 0.011, -0.0752))
    hb.add(M.black_plastic, lambda bm: U.box(bm, -0.024, -0.016, -0.0762, 0.024, 0.016, -0.0748))
    for bx in (-0.012, 0.012):
        hb.add(M.panel_led, lambda bm, bx=bx: U.cyl(bm, 0.003, -0.0775, -0.0755, x=bx, y=-0.024, seg=16))
    h = hb.obj(coll, bevel=0.0012, seg=1)
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    h.matrix_world = Matrix.Translation(head) @ rot
    # Yoke from the stand to the head's pivots.
    yk = MB(name + "_yoke")

    def yoke(bm):
        U.box(bm, -0.074, -0.006, -0.004, 0.074, 0.006, 0.004)
        U.box(bm, -0.074, -0.006, 0.0, -0.068, 0.006, 0.07)
        U.box(bm, 0.068, -0.006, 0.0, 0.074, 0.006, 0.07)
    yk.add(M.black_oxide, yoke)
    y = yk.obj(coll, bevel=0.001, seg=1)
    yaw = math.atan2(d.y, d.x) - math.pi / 2
    y.matrix_world = Matrix.Translation(head - Vector((0, 0, 0.07))) @ Matrix.Rotation(yaw, 4, "Z")
    # The light itself, just in front of the lens.
    L = bpy.data.lights.new(name + "_spot", "SPOT")
    L.energy = power
    L.color = rgb
    L.spot_size = math.radians(34)
    L.spot_blend = 0.55
    L.shadow_soft_size = 0.035
    lo = bpy.data.objects.new(name + "_spot", L)
    coll.objects.link(lo)
    lo.matrix_world = Matrix.Translation(head + d * 0.045) @ d.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    lo["parts"] = [h.name, y.name, name + "_stand"]
    return lo


def can_light(coll, M, name, loc, aim, rgb, power=25.0):
    """A small floor 'can' uplight with a coloured gel."""
    loc, aim = Vector(loc), Vector(aim)
    pivot = loc + Vector((0, 0, 0.055))
    d = (aim - pivot).normalized()
    mb = MB(name)
    mb.add(M.black_oxide, lambda bm: U.box(bm, -0.05, -0.012, 0.0, 0.05, 0.012, 0.006))
    for s in (-1, 1):
        mb.add(M.black_oxide, lambda bm, s=s: U.box(bm, s * 0.047 - 0.003, -0.01, 0.0, s * 0.047 + 0.003, 0.01, 0.06))
    base = mb.obj(coll, bevel=0.001, seg=1)
    base.matrix_world = Matrix.Translation(loc) @ Matrix.Rotation(math.atan2(d.y, d.x) - math.pi / 2, 4, "Z")
    hb = MB(name + "_head")
    hb.add(M.black_oxide, lambda bm: lathe(bm, [(0.0, -0.05), (0.036, -0.05), (0.042, -0.04), (0.042, 0.045),
                                                (0.045, 0.05), (0.038, 0.05), (0.038, 0.046), (0.0, 0.046)], seg=48))
    hb.add(emissive(name + "_gel", rgb, 0.8), lambda bm: U.cyl(bm, 0.037, 0.046, 0.047, seg=48))
    h = hb.obj(coll, bevel=0.001, seg=1)
    h.matrix_world = Matrix.Translation(pivot) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    Lg = bpy.data.lights.new(name + "_spot", "SPOT")
    Lg.energy = power
    Lg.color = rgb
    Lg.spot_size = math.radians(55)
    Lg.spot_blend = 0.6
    Lg.shadow_soft_size = 0.03
    lo = bpy.data.objects.new(name + "_spot", Lg)
    coll.objects.link(lo)
    lo.matrix_world = Matrix.Translation(pivot + d * 0.05) @ d.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    return lo


def area(coll, name, loc, aim, size, power, rgb=(1, 1, 1), visible=False):
    Lg = bpy.data.lights.new(name, "AREA")
    Lg.shape = "RECTANGLE"
    Lg.size, Lg.size_y = size
    Lg.energy = power
    Lg.color = rgb
    o = bpy.data.objects.new(name, Lg)
    coll.objects.link(o)
    d = (Vector(aim) - Vector(loc)).normalized()
    o.matrix_world = Matrix.Translation(loc) @ d.to_track_quat("-Z", "Y").to_matrix().to_4x4()
    o.visible_camera = visible
    o.visible_glossy = visible
    o.visible_volume_scatter = visible     # helper lights stay out of the haze
    return o


def link_to(light_obj, receivers, name):
    """Cycles light linking: light_obj only lights the given objects (instancers work too)."""
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    for r in receivers:
        if r.name not in c.objects:
            c.objects.link(r)
    light_obj.light_linking.receiver_collection = c
    return c


def camera(coll, name, loc, target, lens=50.0, fstop=5.6, focus=None, shift=(0, 0)):
    cam = bpy.data.cameras.new(name)
    cam.lens = lens
    cam.sensor_width = 36
    cam.clip_start = 0.01
    cam.clip_end = 50
    cam.shift_x, cam.shift_y = shift
    o = bpy.data.objects.new(name, cam)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = fstop
    cam.dof.focus_distance = (Vector(focus if focus else target) - Vector(loc)).length
    cam.dof.aperture_blades = 7
    return o


def world_and_render(scene, samples=256, haze=0.0):
    w = bpy.data.worlds.new("World")
    scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.004, 0.0045, 0.006, 1)
    bg.inputs["Strength"].default_value = 1.0
    if haze:
        # A little haze in the air, so the lamps' beams read.
        nt = w.node_tree
        vs = nt.nodes.new("ShaderNodeVolumeScatter")
        vs.inputs["Density"].default_value = haze
        vs.inputs["Anisotropy"].default_value = 0.35
        nt.links.new(vs.outputs[0], nt.nodes["World Output"].inputs["Volume"])
        scene.cycles.volume_step_rate = 4.0
        scene.cycles.volume_max_steps = 256
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type == "METAL"
    c = scene.cycles
    c.device = "GPU"
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.012
    c.use_denoising = True
    c.denoiser = "OPENIMAGEDENOISE"
    c.max_bounces = 10
    c.glossy_bounces = 6
    c.transmission_bounces = 8
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.use_light_tree = True
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    # Khronos PBR Neutral keeps the paint's orange and the lamps' colours true; AgX
    # desaturates them. Exposure is set for the orange, not for the dark enclosure.
    scene.view_settings.view_transform = "Khronos PBR Neutral"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = -0.9
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "8"
