"""
1. Import T_SandRipple_N (wind ripple normal map)
2. MI_BlackStorm: ink-black, heavy, low-scattering volumetric cloud instance
3. Rebuild SM_DuneTerrain with bigger, physical rolling dunes (same mesh size / material / collision)
terrain_height() here MUST match the copy used to re-seat the spikes in the level.
"""
import math
import unreal
import warnings

warnings.simplefilter("ignore")

ROOT = "/Game/SpikeField"
SAND_DIR = "J:/Games/Repsyche/Repsyche/Scripts/sand_textures"
TERRAIN_SIZE = 64000.0
TERRAIN_CELLS = 192
SPAWN_CLEAR_RADIUS = 4500.0

atools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(m):
    unreal.log("DUNESTORM " + str(m))


# ------------------------------------------------------------------ 1. normal map
task = unreal.AssetImportTask()
task.filename = SAND_DIR + "/T_SandRipple_N.png"
task.destination_path = ROOT + "/Textures"
task.destination_name = "T_SandRipple_N"
task.replace_existing = True
task.automated = True
task.save = False
atools.import_asset_tasks([task])
tex = eal.load_asset(ROOT + "/Textures/T_SandRipple_N")
tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
tex.set_editor_property("srgb", False)
tex.set_editor_property("filter", unreal.TextureFilter.TF_TRILINEAR)
eal.save_loaded_asset(tex)
log("normal map ok")

# ------------------------------------------------------------------ 2. black storm clouds
parent = unreal.load_object(None, "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud.m_SimpleVolumetricCloud")
mi_path = ROOT + "/Materials/MI_BlackStorm"
if eal.does_asset_exist(mi_path):
    mi = eal.load_asset(mi_path)
else:
    mi = atools.create_asset("MI_BlackStorm", ROOT + "/Materials", unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(mi, parent)
V = unreal.LinearColor
mel.set_material_instance_scalar_parameter_value(mi, "Cloud_GlobalDensity", 0.20)      # 10x the previous 0.02 (25x engine default)
mel.set_material_instance_scalar_parameter_value(mi, "Cloud_GlobalCoverage", 0.25)     # more of the sky covered
mel.set_material_instance_vector_parameter_value(mi, "Cloud_AlbedoColor", V(0.02, 0.02, 0.02, 0.5))       # ink black
mel.set_material_instance_vector_parameter_value(mi, "Multiscatter_Controls", V(0.25, 0.10, 0.07, 1.0))   # lowered scattering
mel.set_material_instance_vector_parameter_value(mi, "Phase_Controls", V(0.5, 0.10, 0.40, 1.0))
mel.set_material_instance_vector_parameter_value(mi, "Layout_WindControls", V(1.0, 0.35, 8.0, 3.0))
mel.set_material_instance_vector_parameter_value(mi, "Noise_Strength", V(1.1, 0.12, 0.06, 2.5))
mel.update_material_instance(mi)
eal.save_loaded_asset(mi)
log("MI_BlackStorm ok")


# ------------------------------------------------------------------ 3. bigger physical dunes
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
    hills += (value_noise(x / 30000.0, y / 30000.0, 41) - 0.5) * 2.0 * 1100.0     # sweeping rolling dunes
    hills += (value_noise(x / 26000.0, y / 26000.0, 77) - 0.5) * 2.0 * 2500.0     # massive rolling dunes (+/-25 m)
    warp = (value_noise(x / 9000.0, y / 9000.0, 5) - 0.5) * 4.0
    ridges = math.sin(x * 0.00042 + y * 0.00012 + warp * 2.3) * 140.0
    ridges += math.sin(x * 0.0011 + y * 0.0004 + warp) * 35.0
    ridges += math.sin(x * 0.0007 - y * 0.0009 + warp * 1.7) * 30.0              # wind-swept crest lines
    r = math.hypot(x, y)
    calm = min(1.0, max(0.35, r / SPAWN_CLEAR_RADIUS))
    return (hills + ridges) * calm


n = TERRAIN_CELLS
half = TERRAIN_SIZE / 2.0
step = TERRAIN_SIZE / n
verts = []
zmin, zmax = 1e9, -1e9
for j in range(n + 1):
    for i in range(n + 1):
        x = -half + i * step
        y = -half + j * step
        z = terrain_height(x, y)
        zmin, zmax = min(zmin, z), max(zmax, z)
        verts.append(unreal.Vector(x, y, z))
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
mesh.add_vertices_to_mesh(unreal.GeometryScript_List.convert_array_to_vector_list(verts))
mesh.add_triangles_to_mesh(unreal.GeometryScript_List.convert_array_to_triangle_list(tris))
unreal.GeometryScript_Normals.recompute_normals(mesh, unreal.GeometryScriptCalculateNormalsOptions())

path = ROOT + "/SM_DuneTerrain"
if eal.does_asset_exist(path):
    eal.delete_asset(path)
res = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(
    mesh, path, unreal.GeometryScriptCreateNewStaticMeshAssetOptions())
sm = res[0] if isinstance(res, (tuple, list)) else res
sm.set_material(0, eal.load_asset(ROOT + "/Materials/M_SilverSand"))
body = sm.get_editor_property("body_setup")
body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
sm.modify()
eal.save_loaded_asset(sm)
log("SM_DuneTerrain rebuilt: height range %.0f .. %.0f UU (%.0f m of relief)" % (zmin, zmax, (zmax - zmin) / 100.0))
