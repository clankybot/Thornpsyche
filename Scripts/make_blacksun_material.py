"""Creates M_BlackSun (unlit black disc + white emissive corona) and reports the default
volumetric-cloud material's parameters so wind can be tuned."""
import unreal
import warnings

warnings.simplefilter("ignore")

ROOT = "/Game/SpikeField/Materials"
atools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary


def log(m):
    unreal.log("SUNGEN " + str(m))


# ---- cloud material introspection
for path in ("/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst",
             "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud"):
    m = eal.load_asset(path)
    if m:
        try:
            log("cloud %s scalars=%s vectors=%s textures=%s" % (
                path, list(mel.get_scalar_parameter_names(m)), list(mel.get_vector_parameter_names(m)),
                list(mel.get_texture_parameter_names(m))))
        except Exception as e:
            log("cloud introspect failed %s: %s" % (path, e))
    else:
        log("cloud material not found: " + path)

# ---- M_BlackSun
name = "M_BlackSun"
path = "%s/%s" % (ROOT, name)
if eal.does_asset_exist(path):
    mat = eal.load_asset(path)
    mel.delete_all_material_expressions(mat)
else:
    mat = atools.create_asset(name, ROOT, unreal.Material, unreal.MaterialFactoryNew())

mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
mat.set_editor_property("two_sided", False)

# Fresnel: 0 at the disc centre (facing the camera) -> 1 at the rim, so the centre stays pure black
fres = mel.create_material_expression(mat, unreal.MaterialExpressionFresnel, -700, 0)
fres.set_editor_property("exponent", 2.2)
fres.set_editor_property("base_reflect_fraction", 0.0)

gain = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -700, 200)
gain.set_editor_property("r", 60.0)                 # HDR corona so bloom spreads it
mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -450, 60)
mel.connect_material_expressions(fres, "", mul, "A")
mel.connect_material_expressions(gain, "", mul, "B")

white = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -450, 200)
white.set_editor_property("constant", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
tint = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -220, 100)
mel.connect_material_expressions(mul, "", tint, "A")
mel.connect_material_expressions(white, "", tint, "B")
mel.connect_material_property(tint, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

mel.recompile_material(mat)
eal.save_loaded_asset(mat)
log("M_BlackSun ok")
