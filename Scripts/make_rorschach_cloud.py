"""
M_RorschachCloud: monochrome silver volumetric-cloud material with flowing, ambiguous,
Rorschach-like ink patterns.

Pipeline (all in world space, animated by Time):
  P0  = (WorldPos + WindDir * Time * WindSpeed) * PatternScale
  P1  = lerp(P0, mirror_x(P0), 0.7)              bilateral, ink-blot symmetry (axis drifts with the wind)
  P2  = P1 + curlNoise(P1 * 0.55 + t*v1) * FlowDistortion        first fluid warp
  P3  = P2 + curlNoise(P2 * 1.35 + t*v2) * FlowDistortion * 0.6  second warp (ink diffusing in fluid)
  f1  = fractal gradient noise(P3)  (6 octaves, turbulence)
  f2  = fractal voronoi noise(P2 * 2.1)   (cells -> blot boundaries)
  ink = smoothstep(cov-0.12, cov+0.18, 0.45*ridge(f1) + 1.1*f1*(1-f2))   cov breathes with sin(t)
  Extinction = ink * altitudeProfile * Density
  Albedo     = grey ramp from dark grey to silver (R=G=B, no tint)
"""
import unreal
import warnings

warnings.simplefilter("ignore")

atools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
ME = unreal

ROOT = "/Game/SpikeField/Materials"
NAME = "M_RorschachCloud"


def log(m):
    unreal.log("RORSCH " + str(m))


path = "%s/%s" % (ROOT, NAME)
if eal.does_asset_exist(path):
    mat = eal.load_asset(path)
    mel.delete_all_material_expressions(mat)
else:
    mat = atools.create_asset(NAME, ROOT, unreal.Material, unreal.MaterialFactoryNew())

mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_VOLUME)
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)

_y = [0]


def mk(cls, x=0, y=None):
    if y is None:
        _y[0] += 90
        y = _y[0]
    return mel.create_material_expression(mat, cls, x, y)


def link(a, b, pin="", out=""):
    mel.connect_material_expressions(a, out, b, pin)


def const(v):
    n = mk(ME.MaterialExpressionConstant)
    n.set_editor_property("r", float(v))
    return n


def vconst(r, g, b):
    n = mk(ME.MaterialExpressionConstant3Vector)
    n.set_editor_property("constant", unreal.LinearColor(r, g, b, 1.0))
    return n


def sparam(name, default):
    n = mk(ME.MaterialExpressionScalarParameter)
    n.set_editor_property("parameter_name", name)
    n.set_editor_property("default_value", float(default))
    return n


def vparam(name, r, g, b):
    n = mk(ME.MaterialExpressionVectorParameter)
    n.set_editor_property("parameter_name", name)
    n.set_editor_property("default_value", unreal.LinearColor(r, g, b, 1.0))
    return n


def binop(cls, a, b):
    n = mk(cls)
    link(a, n, "A")
    link(b, n, "B")
    return n


def mul(a, b): return binop(ME.MaterialExpressionMultiply, a, b)
def add(a, b): return binop(ME.MaterialExpressionAdd, a, b)
def sub(a, b): return binop(ME.MaterialExpressionSubtract, a, b)
def div(a, b): return binop(ME.MaterialExpressionDivide, a, b)


def unary(cls, a, pin=""):
    n = mk(cls)
    link(a, n, pin)
    return n


def lerp(a, b, alpha):
    n = mk(ME.MaterialExpressionLinearInterpolate)
    link(a, n, "A")
    link(b, n, "B")
    link(alpha, n, "Alpha")
    return n


def mask(src, r=False, g=False, b=False):
    n = mk(ME.MaterialExpressionComponentMask)
    n.set_editor_property("r", r)
    n.set_editor_property("g", g)
    n.set_editor_property("b", b)
    n.set_editor_property("a", False)
    link(src, n)
    return n


def power(base, exp):
    n = mk(ME.MaterialExpressionPower)
    link(base, n, "Base")
    link(exp, n, "Exponent")
    return n


# ------------------------------------------------------------------ parameters (exposed "timeline" controls)
p_wind = sparam("WindSpeed", 2500.0)          # UU / second along WindDirection
p_churn = sparam("ChurnSpeed", 1.0)           # multiplies the internal flow clock
p_dir = vparam("WindDirection", 1.0, 0.45, 0.0)
p_scale = sparam("PatternScale", 1.0 / 22000.0)
p_dens = sparam("Density", 0.02)
p_cover = sparam("Coverage", 0.52)
p_warp = sparam("FlowDistortion", 1.6)

t_raw = mk(ME.MaterialExpressionTime)
t = mul(t_raw, p_churn)                       # churn clock

# ------------------------------------------------------------------ coordinates
wp = mk(ME.MaterialExpressionWorldPosition)
wind_off = mul(p_dir, mul(t_raw, p_wind))
P0 = mul(add(wp, wind_off), p_scale)

# bilateral (Rorschach) mirror on x, blended so it never becomes a perfect mirror
px = mask(P0, r=True)
pyz = mask(P0, g=True, b=True)
mirror = mk(ME.MaterialExpressionAppendVector)
link(unary(ME.MaterialExpressionAbs, px), mirror, "A")
link(pyz, mirror, "B")
P1 = lerp(P0, mirror, const(0.7))


def curl(pos):
    n = mk(ME.MaterialExpressionVectorNoise)
    n.set_editor_property("noise_function", unreal.VectorNoiseFunction.VNF_CURL_ALU)
    n.set_editor_property("quality", 1)
    link(pos, n, "Position")
    return n


# fluid warp 1
a1 = add(mul(P1, const(0.55)), mul(vconst(0.13, -0.09, 0.07), t))
P2 = add(P1, mul(curl(a1), p_warp))
# fluid warp 2 (different scale, speed and direction -> ink diffusing through a moving fluid)
a2 = add(mul(P2, const(1.35)), mul(vconst(-0.17, 0.11, -0.05), t))
P3 = add(P2, mul(curl(a2), mul(p_warp, const(0.6))))


def fractal(pos, fn, levels, lscale):
    n = mk(ME.MaterialExpressionNoise)
    n.set_editor_property("noise_function", fn)
    n.set_editor_property("levels", levels)
    n.set_editor_property("level_scale", lscale)
    n.set_editor_property("turbulence", True)
    n.set_editor_property("output_min", 0.0)
    n.set_editor_property("output_max", 1.0)
    n.set_editor_property("scale", 1.0)
    link(pos, n, "Position")
    return n


f1 = fractal(add(P3, mul(vconst(0.05, 0.08, -0.06), t)), unreal.NoiseFunction.NOISEFUNCTION_GRADIENT_ALU, 6, 2.0)
f2 = fractal(add(mul(P2, const(2.1)), mul(vconst(-0.11, 0.06, 0.09), t)), unreal.NoiseFunction.NOISEFUNCTION_VORONOI_ALU, 3, 2.0)

# ------------------------------------------------------------------ non-linear ink shaping
ridge = unary(ME.MaterialExpressionOneMinus, unary(ME.MaterialExpressionAbs, sub(mul(f1, const(2.0)), const(1.0))))
blot = mul(f1, unary(ME.MaterialExpressionOneMinus, f2))
mixed = add(mul(ridge, const(0.45)), mul(blot, const(1.1)))

breath = mul(unary(ME.MaterialExpressionSine, mul(t, const(0.21))), const(0.08))   # coverage breathes; pattern never settles
cov = add(p_cover, breath)
ss = mk(ME.MaterialExpressionSmoothStep)
link(sub(cov, const(0.12)), ss, "Min")
link(add(cov, const(0.18)), ss, "Max")
link(mixed, ss, "Value")
ink = ss

# altitude profile: cloud layer 5 km .. 15 km above the planet-top origin (matches the component settings)
z = mask(wp, b=True)
alt = unary(ME.MaterialExpressionSaturate, div(sub(z, const(500000.0)), const(1000000.0)))
profile = mul(mul(const(4.0), alt), unary(ME.MaterialExpressionOneMinus, alt))

white = vconst(1.0, 1.0, 1.0)
extinction = mul(mul(mul(ink, profile), p_dens), white)

# ------------------------------------------------------------------ strictly monochrome silver albedo
lum = lerp(const(0.10), const(0.88), power(ink, const(0.7)))
lum = add(lum, mul(ridge, const(0.06)))                # faint metallic sheen along the ink veins
albedo = mul(unary(ME.MaterialExpressionSaturate, lum), white)
emissive = mul(mul(ink, const(0.015)), white)

mel.connect_material_property(albedo, "", unreal.MaterialProperty.MP_BASE_COLOR)              # Albedo
mel.connect_material_property(extinction, "", unreal.MaterialProperty.MP_SUBSURFACE_COLOR)    # Extinction
mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

mel.recompile_material(mat)
eal.save_loaded_asset(mat)
log("%s built and saved" % NAME)

# ------------------------------------------------------------------ instance with fast wind / churn
mi_path = "%s/MI_RorschachCloud" % ROOT
if eal.does_asset_exist(mi_path):
    mi = eal.load_asset(mi_path)
else:
    mi = atools.create_asset("MI_RorschachCloud", ROOT, unreal.MaterialInstanceConstant,
                             unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(mi, mat)
mel.set_material_instance_scalar_parameter_value(mi, "WindSpeed", 9000.0)       # 3.6x the material default
mel.set_material_instance_scalar_parameter_value(mi, "ChurnSpeed", 3.0)         # 3x
mel.set_material_instance_scalar_parameter_value(mi, "FlowDistortion", 2.0)
mel.update_material_instance(mi)
eal.save_loaded_asset(mi)
log("MI_RorschachCloud saved")
