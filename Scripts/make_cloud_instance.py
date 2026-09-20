"""MI_GiediClouds: churning, fast-wind volumetric cloud material instance."""
import unreal
import warnings

warnings.simplefilter("ignore")

atools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

PATH = "/Game/SpikeField/Materials/MI_GiediClouds"
parent = unreal.load_object(None, "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud.m_SimpleVolumetricCloud")

if eal.does_asset_exist(PATH):
    mi = eal.load_asset(PATH)
else:
    mi = atools.create_asset("MI_GiediClouds", "/Game/SpikeField/Materials",
                             unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(mi, parent)

# Layout_WindControls: rg = wind direction, b = wind speed, a = cloud-shape animation speed
mel.set_material_instance_vector_parameter_value(mi, "Layout_WindControls", unreal.LinearColor(1.0, 0.35, 8.0, 3.0))
mel.set_material_instance_scalar_parameter_value(mi, "Cloud_GlobalCoverage", 0.15)     # denser cover
mel.set_material_instance_scalar_parameter_value(mi, "Cloud_GlobalDensity", 0.02)
mel.set_material_instance_vector_parameter_value(mi, "Cloud_AlbedoColor", unreal.LinearColor(0.6, 0.6, 0.6, 0.5))
mel.set_material_instance_vector_parameter_value(mi, "Noise_Strength", unreal.LinearColor(1.1, 0.12, 0.06, 2.5))  # more turbulent
mel.update_material_instance(mi)
eal.save_loaded_asset(mi)
unreal.log("CLOUDGEN MI_GiediClouds ok, parent=%s" % mi.get_editor_property("parent"))
