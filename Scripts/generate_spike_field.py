"""
Procedural "Spike Field" generator for Unreal Engine 5.8.

Run headless with:
  UnrealEditor-Cmd.exe Repsyche.uproject -run=pythonscript -script=generate_spike_field.py -unattended -nullrhi

Builds (all under /Game/SpikeField):
  * T_SilverSand_D / T_SilverSand_R   imported from SAND_DIR
  * M_SilverSand                      world-space tiled sand master material
  * M_SpikeBlack                      matte black, non-reflective
  * SM_Megalith                       stacked, dry-stack-jointed tapered megalith
  * SM_DuneTerrain                    64 km x 64 km undulating dune mesh
  * Lvl_SpikeField                    level: terrain, Poisson-placed spikes, lighting,
                                      PlayerStart and BP_Enemy actors

NOTE: A true Landscape actor cannot be created from the Python API (there is no way
to create landscape components), so the dunes are a static mesh with complex-as-simple
collision.
"""
import math
import random
import warnings

import unreal

warnings.simplefilter("ignore")

# ---------------------------------------------------------------- config
SAND_DIR = "J:/Games/Repsyche/Repsyche/Scripts/sand_textures"   # produced by make_sand.py
ROOT = "/Game/SpikeField"
LEVEL = ROOT + "/Lvl_SpikeField"
SEED = 1337

TERRAIN_SIZE = 64000.0        # UU (640 m)
TERRAIN_CELLS = 192           # quads per side
DUNE_TILE_UU = 350.0          # sand texture repeat length

MEGALITH_HEIGHT = 2000.0      # 20 m above ground at scale 1.0 (50 m at 2.5x)
MEGALITH_BURY = 500.0         # buried below the pivot so dunes/lean never expose the base
BASE_W, BASE_D = 560.0, 420.0
TIP_W, TIP_D = 50.0, 40.0
MIN_CLEAR_GAP = 1500.0        # minimum open sand between any two spike footprints
SCALE_MIN, SCALE_MAX = 1.0, 2.5
LEAN_MAX_DEG = 15.0
SPAWN_CLEAR_RADIUS = 4500.0   # open arena around the origin for PlayerStart + enemies
EDGE_MARGIN = 3500.0
TARGET_SPIKES = 90
NUM_ENEMIES = 5

rng = random.Random(SEED)
atools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(msg):
    unreal.log("SPIKEGEN " + str(msg))


# ---------------------------------------------------------------- textures
def import_texture(fname, name, srgb):
    task = unreal.AssetImportTask()
    task.filename = "%s/%s" % (SAND_DIR, fname)
    task.destination_path = ROOT + "/Textures"
    task.destination_name = name
    task.replace_existing = True
    task.automated = True
    task.save = False
    atools.import_asset_tasks([task])
    tex = eal.load_asset("%s/Textures/%s" % (ROOT, name))
    tex.set_editor_property("srgb", srgb)
    if not srgb:
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    tex.set_editor_property("filter", unreal.TextureFilter.TF_TRILINEAR)
    eal.save_loaded_asset(tex)
    log("texture %s ok" % name)
    return tex


# ---------------------------------------------------------------- materials
def new_material(name):
    path = "%s/Materials/%s" % (ROOT, name)
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)   # reuse: safe to re-run the generator
        return mat
    return atools.create_asset(name, ROOT + "/Materials", unreal.Material, unreal.MaterialFactoryNew())


def expr(mat, cls, x, y):
    return mel.create_material_expression(mat, cls, x, y)


def build_sand_material(tex_d, tex_r):
    mat = new_material("M_SilverSand")
    wp = expr(mat, unreal.MaterialExpressionWorldPosition, -1400, 0)
    mask = expr(mat, unreal.MaterialExpressionComponentMask, -1200, 0)
    mask.set_editor_property("r", True)
    mask.set_editor_property("g", True)
    mask.set_editor_property("b", False)
    mask.set_editor_property("a", False)
    mel.connect_material_expressions(wp, "", mask, "")

    scale_fine = expr(mat, unreal.MaterialExpressionConstant, -1200, 200)
    scale_fine.set_editor_property("r", 1.0 / DUNE_TILE_UU)
    uv_fine = expr(mat, unreal.MaterialExpressionMultiply, -1000, 60)
    mel.connect_material_expressions(mask, "", uv_fine, "A")
    mel.connect_material_expressions(scale_fine, "", uv_fine, "B")

    scale_macro = expr(mat, unreal.MaterialExpressionConstant, -1200, 320)
    scale_macro.set_editor_property("r", 1.0 / (DUNE_TILE_UU * 23.0))
    uv_macro = expr(mat, unreal.MaterialExpressionMultiply, -1000, 240)
    mel.connect_material_expressions(mask, "", uv_macro, "A")
    mel.connect_material_expressions(scale_macro, "", uv_macro, "B")

    s_d = expr(mat, unreal.MaterialExpressionTextureSample, -700, -100)
    s_d.set_editor_property("texture", tex_d)
    mel.connect_material_expressions(uv_fine, "", s_d, "UVs")

    s_m = expr(mat, unreal.MaterialExpressionTextureSample, -700, 120)
    s_m.set_editor_property("texture", tex_d)
    mel.connect_material_expressions(uv_macro, "", s_m, "UVs")

    # macro variation: albedo * (0.82 + 0.36 * macro.r)  -> breaks tiling on a 640 m field
    k_mul = expr(mat, unreal.MaterialExpressionConstant, -500, 200)
    k_mul.set_editor_property("r", 0.36)
    m_mul = expr(mat, unreal.MaterialExpressionMultiply, -350, 140)
    mel.connect_material_expressions(s_m, "R", m_mul, "A")
    mel.connect_material_expressions(k_mul, "", m_mul, "B")
    k_add = expr(mat, unreal.MaterialExpressionConstant, -350, 260)
    k_add.set_editor_property("r", 0.82)
    m_add = expr(mat, unreal.MaterialExpressionAdd, -200, 160)
    mel.connect_material_expressions(m_mul, "", m_add, "A")
    mel.connect_material_expressions(k_add, "", m_add, "B")
    base = expr(mat, unreal.MaterialExpressionMultiply, 0, -60)
    mel.connect_material_expressions(s_d, "RGB", base, "A")
    mel.connect_material_expressions(m_add, "", base, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # dynamic roughness map: bright grains glossier, dark grains matte
    s_r = expr(mat, unreal.MaterialExpressionTextureSample, -700, 360)
    s_r.set_editor_property("texture", tex_r)
    s_r.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    mel.connect_material_expressions(uv_fine, "", s_r, "UVs")
    mel.connect_material_property(s_r, "R", unreal.MaterialProperty.MP_ROUGHNESS)

    spec = expr(mat, unreal.MaterialExpressionConstant, -300, 420)
    spec.set_editor_property("r", 0.6)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)

    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    log("M_SilverSand ok")
    return mat


def build_spike_material():
    mat = new_material("M_SpikeBlack")
    col = expr(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
    col.set_editor_property("constant", unreal.LinearColor(0.003, 0.003, 0.003, 1.0))
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = expr(mat, unreal.MaterialExpressionConstant, -400, 150)
    rough.set_editor_property("r", 1.0)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    spec = expr(mat, unreal.MaterialExpressionConstant, -400, 300)
    spec.set_editor_property("r", 0.0)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat)
    log("M_SpikeBlack ok")
    return mat


# ---------------------------------------------------------------- meshes
def make_static_mesh(dyn_mesh, path):
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
    res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dyn_mesh, path, opts)
    sm = res[0] if isinstance(res, (tuple, list)) else res
    return sm


def set_complex_as_simple(sm):
    flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    try:
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        sub.set_collision_complexity(sm, flag)
    except Exception as e:
        log("subsystem collision setter unavailable (%s); setting body setup directly" % str(e).split("\n")[0])
        body = sm.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", flag)
        sm.modify()
    body = sm.get_editor_property("body_setup")
    log("collision trace flag on %s = %s" % (sm.get_name(), body.get_editor_property("collision_trace_flag")))


def build_megalith(mat_black):
    """Stacked tapered blocks with recessed dry-stack joints, each block slightly twisted/offset."""
    mesh = unreal.DynamicMesh()
    total = MEGALITH_HEIGHT + MEGALITH_BURY
    # block heights: chunky at the base, finer toward the tip
    n = 17
    weights = [1.0 + 0.9 * (1.0 - i / (n - 1.0)) for i in range(n)]
    sw = sum(weights)
    heights = [total * w / sw for w in weights]
    z = -MEGALITH_BURY
    r = random.Random(SEED + 1)
    prim_opts = unreal.GeometryScriptPrimitiveOptions()
    for i, h in enumerate(heights):
        t = max(0.0, min(1.0, (z + h * 0.5 + MEGALITH_BURY) / total))
        w = BASE_W + (TIP_W - BASE_W) * (t ** 0.9)
        d = BASE_D + (TIP_D - BASE_D) * (t ** 0.9)
        ox = r.uniform(-w * 0.03, w * 0.03)
        oy = r.uniform(-d * 0.03, d * 0.03)
        yaw = r.uniform(-4.0, 4.0)
        gap = 8.0
        xf = unreal.Transform(unreal.Vector(ox, oy, z), unreal.Rotator(0.0, 0.0, yaw), unreal.Vector(1, 1, 1))
        unreal.GeometryScript_Primitives.append_box(
            mesh, prim_opts, xf, w, d, h - gap, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        # recessed keyed joint filling the gap so the seam reads as a dark groove
        jw, jd = w * 0.86, d * 0.86
        xf_j = unreal.Transform(unreal.Vector(ox, oy, z + h - gap - 2.0), unreal.Rotator(0.0, 0.0, yaw), unreal.Vector(1, 1, 1))
        unreal.GeometryScript_Primitives.append_box(
            mesh, prim_opts, xf_j, jw, jd, gap + 4.0, 0, 0, 0, unreal.GeometryScriptPrimitiveOriginMode.BASE)
        z += h
    sm = make_static_mesh(mesh, ROOT + "/SM_Megalith")
    sm.set_material(0, mat_black)
    set_complex_as_simple(sm)
    eal.save_loaded_asset(sm)
    log("SM_Megalith ok")
    return sm


# ---------------------------------------------------------------- terrain
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
    """Gentle undulating silver dunes: low broad hills + wind-aligned dune ridges."""
    hills = (value_noise(x / 14000.0, y / 14000.0, 11) - 0.5) * 2.0 * 420.0
    hills += (value_noise(x / 5200.0, y / 5200.0, 23) - 0.5) * 2.0 * 160.0
    warp = (value_noise(x / 9000.0, y / 9000.0, 5) - 0.5) * 4.0
    ridges = math.sin(x * 0.00042 + y * 0.00012 + warp * 2.3) * 85.0
    ridges += math.sin(x * 0.0011 + y * 0.0004 + warp) * 22.0
    # keep the central arena a bit calmer
    r = math.hypot(x, y)
    calm = min(1.0, max(0.35, r / SPAWN_CLEAR_RADIUS))
    return (hills + ridges) * calm


def build_terrain(mat_sand):
    n = TERRAIN_CELLS
    half = TERRAIN_SIZE / 2.0
    step = TERRAIN_SIZE / n
    verts = []
    for j in range(n + 1):
        for i in range(n + 1):
            x = -half + i * step
            y = -half + j * step
            verts.append(unreal.Vector(x, y, terrain_height(x, y)))
    tris = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            b = a + 1
            c = a + (n + 1)
            d = c + 1
            tris.append(unreal.IntVector(a, c, b))
            tris.append(unreal.IntVector(b, c, d))
    mesh = unreal.DynamicMesh()
    vlist = unreal.GeometryScript_List.convert_array_to_vector_list(verts)
    tlist = unreal.GeometryScript_List.convert_array_to_triangle_list(tris)
    mesh.add_vertices_to_mesh(vlist)
    mesh.add_triangles_to_mesh(tlist)
    unreal.GeometryScript_Normals.recompute_normals(mesh, unreal.GeometryScriptCalculateNormalsOptions())
    sm = make_static_mesh(mesh, ROOT + "/SM_DuneTerrain")
    sm.set_material(0, mat_sand)
    set_complex_as_simple(sm)
    eal.save_loaded_asset(sm)
    log("SM_DuneTerrain ok (%d verts, %d tris)" % (len(verts), len(tris)))
    return sm


# ---------------------------------------------------------------- placement
def footprint_radius(scale):
    return 0.5 * math.hypot(BASE_W, BASE_D) * scale


def poisson_place():
    """Dart-throwing Poisson-disc variant: every accepted pair keeps >= MIN_CLEAR_GAP of open
    ground between footprints (center distance >= gap + r_a + r_b). Also keeps the spawn arena clear."""
    placed = []
    half = TERRAIN_SIZE / 2.0 - EDGE_MARGIN
    attempts = 0
    while len(placed) < TARGET_SPIKES and attempts < 60000:
        attempts += 1
        s = rng.uniform(SCALE_MIN, SCALE_MAX)
        r = footprint_radius(s) + math.sin(math.radians(LEAN_MAX_DEG)) * 0.0
        x = rng.uniform(-half, half)
        y = rng.uniform(-half, half)
        if math.hypot(x, y) < SPAWN_CLEAR_RADIUS + r:
            continue
        ok = True
        for (px, py, ps, pr) in placed:
            if math.hypot(x - px, y - py) < MIN_CLEAR_GAP + r + pr:
                ok = False
                break
        if ok:
            placed.append((x, y, s, r))
    log("placed %d spikes in %d attempts" % (len(placed), attempts))
    return placed


# ---------------------------------------------------------------- level
def set_prop(obj, name, value):
    try:
        obj.set_editor_property(name, value)
        return True
    except Exception as e:
        log("  could not set %s: %s" % (name, str(e).split("\n")[0]))
        return False


def build_level(sm_terrain, sm_megalith, placed):
    if eal.does_asset_exist(LEVEL):
        eal.delete_asset(LEVEL)
    ok = unreal.EditorLevelLibrary.new_level(LEVEL)
    log("new_level -> %s" % ok)
    ell = unreal.EditorLevelLibrary
    world = ell.get_editor_world()

    # game mode
    try:
        gm = eal.load_blueprint_class("/Game/Characters/GM_Whitebot")
        world.get_world_settings().set_editor_property("default_game_mode", gm)
    except Exception as e:
        log("game mode override failed: %s" % e)

    def spawn_sm(sm, loc, rot, scale, label, folder):
        a = ell.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
        comp = a.static_mesh_component
        comp.set_mobility(unreal.ComponentMobility.STATIC)
        comp.set_static_mesh(sm)
        a.set_actor_scale3d(scale)
        a.set_actor_label(label)
        a.set_folder_path(folder)
        return a

    spawn_sm(sm_terrain, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0), unreal.Vector(1, 1, 1), "DuneTerrain", "Terrain")

    r = random.Random(SEED + 2)
    for i, (x, y, s, _rad) in enumerate(placed):
        z = terrain_height(x, y)
        pitch = r.uniform(-LEAN_MAX_DEG, LEAN_MAX_DEG)
        roll = r.uniform(-LEAN_MAX_DEG, LEAN_MAX_DEG)
        yaw = r.uniform(0.0, 360.0)
        spawn_sm(sm_megalith, unreal.Vector(x, y, z), unreal.Rotator(roll, pitch, yaw),
                 unreal.Vector(s, s, s), "Megalith_%03d" % i, "Megaliths")

    # ---- lighting
    sun = ell.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 3000), unreal.Rotator(0.0, -20.0, 40.0))
    sun.set_actor_label("HarshSun")
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    set_prop(lc, "intensity", 50.0)
    set_prop(lc, "light_color", unreal.Color(255, 255, 255, 255))
    set_prop(lc, "light_source_angle", 0.0)          # no soft penumbra
    set_prop(lc, "light_source_soft_angle", 0.0)
    set_prop(lc, "cast_shadows", True)
    set_prop(lc, "dynamic_shadow_distance_movable_light", 40000.0)
    set_prop(lc, "dynamic_shadow_cascades", 5)
    set_prop(lc, "cascade_distribution_exponent", 3.5)
    set_prop(lc, "atmosphere_sun_light", True)
    set_prop(lc, "mobility", unreal.ComponentMobility.MOVABLE)

    sky = ell.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    sac = sky.get_component_by_class(unreal.SkyAtmosphereComponent)
    # A 20-degree sun through a normal blue-weighted atmosphere reads as sunset (orange).
    # Neutral (achromatic) Rayleigh scattering + strong Mie haze gives the bright, silvery,
    # overcast sky of the reference.
    set_prop(sac, "rayleigh_scattering", unreal.LinearColor(0.5, 0.5, 0.5, 30.2))
    set_prop(sac, "rayleigh_scattering_scale", 0.35)
    set_prop(sac, "mie_scattering_scale", 0.14)
    set_prop(sac, "mie_absorption_scale", 0.0)
    set_prop(sac, "sky_luminance_factor", unreal.LinearColor(1.2, 1.2, 1.2, 1.0))
    set_prop(sac, "multi_scattering_factor", 1.0)

    sl = ell.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500), unreal.Rotator(0, 0, 0))
    slc = sl.get_component_by_class(unreal.SkyLightComponent)
    set_prop(slc, "real_time_capture", True)
    set_prop(slc, "intensity", 1.6)
    set_prop(slc, "mobility", unreal.ComponentMobility.MOVABLE)

    fog = ell.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    set_prop(fc, "fog_density", 0.0025)
    set_prop(fc, "fog_height_falloff", 0.05)
    set_prop(fc, "start_distance", 6000.0)
    set_prop(fc, "fog_inscattering_luminance", unreal.LinearColor(0.75, 0.8, 0.88, 1.0))

    ppv = ell.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    ppv.set_actor_label("GrainyHighContrastPP")
    set_prop(ppv, "unbound", True)
    st = ppv.get_editor_property("settings")
    for k, v in (("override_film_grain_intensity", True), ("film_grain_intensity", 0.4),
                 ("override_film_grain_intensity_shadows", True), ("film_grain_intensity_shadows", 0.5),
                 ("override_color_contrast", True), ("color_contrast", unreal.Vector4(1.25, 1.25, 1.25, 1.0)),
                 ("override_bloom_intensity", True), ("bloom_intensity", 0.15)):
        try:
            st.set_editor_property(k, v)
        except Exception as e:
            log("  pp %s: %s" % (k, str(e).split("\n")[0]))
    ppv.set_editor_property("settings", st)

    # ---- player start + enemies in the open arena
    ps_z = terrain_height(0, 0) + 120.0
    ps = ell.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(0, 0, ps_z), unreal.Rotator(0, 0, 0))
    ps.set_actor_label("PlayerStart")
    enemy_cls = eal.load_blueprint_class("/Game/Characters/BP_Enemy")
    for i in range(NUM_ENEMIES):
        ang = (i / float(NUM_ENEMIES)) * 2.0 * math.pi + 0.4
        dist = 2200.0 + 300.0 * (i % 2)
        ex, ey = math.cos(ang) * dist, math.sin(ang) * dist
        e = ell.spawn_actor_from_class(enemy_cls, unreal.Vector(ex, ey, terrain_height(ex, ey) + 120.0),
                                       unreal.Rotator(0, 0, math.degrees(ang) + 180.0))
        e.set_actor_label("Enemy_%d" % i)
        e.set_folder_path("Enemies")

    saved = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL)
    log("level saved (dirty packages saved: %s)" % saved)


# ---------------------------------------------------------------- main
def main():
    eal.make_directory(ROOT)
    eal.make_directory(ROOT + "/Textures")
    eal.make_directory(ROOT + "/Materials")
    tex_d = import_texture("T_SilverSand_D.png", "T_SilverSand_D", True)
    tex_r = import_texture("T_SilverSand_R.png", "T_SilverSand_R", False)
    mat_sand = build_sand_material(tex_d, tex_r)
    mat_black = build_spike_material()
    sm_meg = build_megalith(mat_black)
    sm_terrain = build_terrain(mat_sand)
    placed = poisson_place()
    build_level(sm_terrain, sm_meg, placed)
    log("DONE")


main()
