"""
Re-spike Lvl_SpikeField.

  * builds SM_Obelisk: a high-polygon, perfectly straight-edged triangular pyramid (no steps / blocks)
  * deletes every existing Megalith_* actor
  * respawns them Poisson-style with extreme randomisation:
        scale Z   5.0 .. 30.0   (unit mesh is 10 m tall -> 50 m .. 300 m spikes)
        scale X,Y 1.0 ..  4.0   (independent)
        yaw       0 .. 360
        pitch/roll -45 .. +45   (aggressive, chaotic lean)
  * keeps >= MIN_CLEAR_GAP of open ground between spike footprints and the spawn arena clear.

Run:  UnrealEditor-Cmd.exe Repsyche.uproject -run=pythonscript -script=respike_level.py -unattended -nullrhi
(the level must not be open in the editor when it is saved from the commandlet)
"""
import math
import random
import warnings

import unreal

warnings.simplefilter("ignore")

ROOT = "/Game/SpikeField"
LEVEL = ROOT + "/Lvl_SpikeField"
MESH_PATH = ROOT + "/SM_Obelisk"
SEED = 2026

TERRAIN_SIZE = 64000.0
SPAWN_CLEAR_RADIUS = 4500.0
EDGE_MARGIN = 4500.0
MIN_CLEAR_GAP = 4000.0
TARGET_SPIKES = 90

SCALE_XY = (8.0, 20.0)
SCALE_Z = (5.0, 30.0)
LEAN_DEG = 45.0

# unit mesh (before scaling): triangular pyramid from z=-200 (buried) to the apex at z=1000
BASE_Z = -200.0
BASE_RADIUS = 140.0
HEIGHT = 1200.0
RADIAL_STEPS = 3          # triangular cross-section -> three flat, razor-straight faces
HEIGHT_STEPS = 48         # high tessellation along the length

# thorn-branches: secondary spikes attached to a main spike
THORN_CHANCE = 0.40
THORN_COUNT = (1, 3)
THORN_SCALE = 0.4                 # relative to the parent (so 40% of the parent's size)
THORN_TILT_DEG = (45.0, 85.0)     # |pitch| and |roll|, random sign each
THORN_Z_RANGE = (200.0, 800.0)    # local Z up the parent mesh (unit mesh runs -200 .. 1000)

eal = unreal.EditorAssetLibrary
rng = random.Random(SEED)


def log(m):
    unreal.log("RESPIKE " + str(m))


# ------------------------------------------------------------------ mesh
def build_obelisk():
    mesh = unreal.DynamicMesh()
    opts = unreal.GeometryScriptPrimitiveOptions()
    xf = unreal.Transform(unreal.Vector(0, 0, BASE_Z), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1))
    unreal.GeometryScript_Primitives.append_cone(
        mesh, opts, xf, BASE_RADIUS, 0.0, HEIGHT, RADIAL_STEPS, HEIGHT_STEPS, True,
        unreal.GeometryScriptPrimitiveOriginMode.BASE)
    unreal.GeometryScript_Normals.recompute_normals(mesh, unreal.GeometryScriptCalculateNormalsOptions())
    if eal.does_asset_exist(MESH_PATH):
        eal.delete_asset(MESH_PATH)
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(
        mesh, MESH_PATH, unreal.GeometryScriptCreateNewStaticMeshAssetOptions())
    sm = res[0] if isinstance(res, (tuple, list)) else res
    sm.set_material(0, eal.load_asset(ROOT + "/Materials/M_SpikeBlack"))
    body = sm.get_editor_property("body_setup")
    body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    sm.modify()
    eal.save_loaded_asset(sm)
    log("SM_Obelisk built")
    return sm


# ------------------------------------------------------------------ terrain height (must match dunes_and_storm.py)
def _hash(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def value_noise(x, y, seed):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = _smooth(x - ix), _smooth(y - iy)
    a = _hash(ix, iy, seed)
    b = _hash(ix + 1, iy, seed)
    c = _hash(ix, iy + 1, seed)
    d = _hash(ix + 1, iy + 1, seed)
    return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy


def terrain_height(x, y):
    hills = (value_noise(x / 14000.0, y / 14000.0, 11) - 0.5) * 2.0 * 700.0
    hills += (value_noise(x / 5200.0, y / 5200.0, 23) - 0.5) * 2.0 * 200.0
    hills += (value_noise(x / 30000.0, y / 30000.0, 41) - 0.5) * 2.0 * 1100.0
    hills += (value_noise(x / 26000.0, y / 26000.0, 77) - 0.5) * 2.0 * 2500.0     # massive rolling dunes (+/-25 m)
    warp = (value_noise(x / 9000.0, y / 9000.0, 5) - 0.5) * 4.0
    ridges = math.sin(x * 0.00042 + y * 0.00012 + warp * 2.3) * 140.0
    ridges += math.sin(x * 0.0011 + y * 0.0004 + warp) * 35.0
    ridges += math.sin(x * 0.0007 - y * 0.0009 + warp * 1.7) * 30.0
    r = math.hypot(x, y)
    calm = min(1.0, max(0.35, r / SPAWN_CLEAR_RADIUS))
    return (hills + ridges) * calm


# ------------------------------------------------------------------ placement
def sample_spikes():
    placed = []
    half = TERRAIN_SIZE / 2.0 - EDGE_MARGIN
    attempts = 0
    while len(placed) < TARGET_SPIKES and attempts < 100000:
        attempts += 1
        sx = rng.uniform(*SCALE_XY)
        sy = rng.uniform(*SCALE_XY)
        sz = rng.uniform(*SCALE_Z)
        r = BASE_RADIUS * max(sx, sy)              # footprint (circumradius of the triangular base)
        x = rng.uniform(-half, half)
        y = rng.uniform(-half, half)
        if math.hypot(x, y) < SPAWN_CLEAR_RADIUS + r:
            continue
        if all(math.hypot(x - p[0], y - p[1]) >= MIN_CLEAR_GAP + r + p[5] for p in placed):
            placed.append((x, y, sx, sy, sz, r))
    log("placed %d spikes in %d attempts" % (len(placed), attempts))
    return placed


def add_thorns(ell, parent, sm, tr, index):
    """40% chance: attach 1-3 small child spikes to `parent`, jutting out of its side like thorns."""
    if tr.random() >= THORN_CHANCE:
        return 0
    n = tr.randint(*THORN_COUNT)
    for k in range(n):
        lz = tr.uniform(*THORN_Z_RANGE)                                  # local Z up the parent
        surf = BASE_RADIUS * (1.0 - (lz - BASE_Z) / HEIGHT)              # parent's radius at that height
        ang = tr.uniform(0.0, 2.0 * math.pi)
        loc = unreal.Vector(math.cos(ang) * surf * 0.8, math.sin(ang) * surf * 0.8, lz)
        pitch = tr.choice((-1, 1)) * tr.uniform(*THORN_TILT_DEG)
        roll = tr.choice((-1, 1)) * tr.uniform(*THORN_TILT_DEG)
        yaw = math.degrees(ang)
        t = ell.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
        c = t.static_mesh_component
        c.set_mobility(unreal.ComponentMobility.STATIC)
        c.set_static_mesh(sm)
        t.attach_to_actor(parent, "", unreal.AttachmentRule.KEEP_RELATIVE,
                          unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE, False)
        c.set_relative_transform(unreal.Transform(loc, unreal.Rotator(roll, pitch, yaw),
                                                  unreal.Vector(THORN_SCALE, THORN_SCALE, THORN_SCALE)),
                                 False, False)
        t.set_actor_label("Thorn_%03d_%d" % (index, k))
        t.set_folder_path("Megaliths/Thorns")
    return n


def main():
    sm = eal.load_asset(MESH_PATH) if eal.does_asset_exist(MESH_PATH) else build_obelisk()

    if not unreal.EditorLevelLibrary.load_level(LEVEL):
        raise RuntimeError("could not load " + LEVEL)
    ell = unreal.EditorLevelLibrary

    removed = 0
    for a in ell.get_all_level_actors():
        if a.get_actor_label().startswith(("Megalith_", "Thorn_")):
            a.destroy_actor()
            removed += 1
    log("deleted %d old spikes/thorns" % removed)

    r = random.Random(SEED + 1)
    thorn_rng = random.Random(SEED + 7)      # separate stream: main spike layout is unchanged
    thorns = 0
    for i, (x, y, sx, sy, sz, _r) in enumerate(sample_spikes()):
        z = terrain_height(x, y)
        pitch = r.uniform(-LEAN_DEG, LEAN_DEG)
        roll = r.uniform(-LEAN_DEG, LEAN_DEG)
        yaw = r.uniform(0.0, 360.0)
        a = ell.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x, y, z),
                                       unreal.Rotator(roll, pitch, yaw))
        c = a.static_mesh_component
        c.set_mobility(unreal.ComponentMobility.STATIC)
        c.set_static_mesh(sm)
        a.set_actor_scale3d(unreal.Vector(sx, sy, sz))
        a.set_actor_label("Megalith_%03d" % i)
        a.set_folder_path("Megaliths")
        thorns += add_thorns(ell, a, sm, thorn_rng, i)
    log("spawned %d thorn-branches" % thorns)

    world = ell.get_editor_world()
    unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL)
    log("level saved")


main()
