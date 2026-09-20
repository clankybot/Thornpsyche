"""Scatter 25 monolithic stylized boulders (scale 15-50) over Lvl_SpikeField. Call run(0, 25).

Runs inside the editor's ProgrammaticToolset sandbox (execute_tool_script): only json/math
are importable, so a small LCG replaces `random`. Call run(start, count) once per batch;
the seed is derived from the actor index so batches are reproducible.
Ground snap: trace straight down; if the first hit is not the lowest surface on that
column (a spike/rock is in the way) the sample is rejected and re-rolled.
"""
import json, math

SC = "editor_toolset.toolsets.scene.SceneTools."
TOTAL_HALF = 30000.0
# XY offset of each mesh's bounds centre from its pivot (FBX kept the source layout)
OFFSETS = [(3, 118), (131, 23), (-171, 71), (2, -88), (235, 15), (168, 149), (50, 55), (159, -61), (-156, -74), (107, 109), (-21, 40)]

def call(tool, **kw):
    return execute_tool(SC + tool, json.dumps(kw))["returnValue"]

def ground_z(x, y):
    hits = []
    z = 20000.0
    for _ in range(4):
        d = call("trace_world", start={"x": x, "y": y, "z": z}, end={"x": x, "y": y, "z": -20000.0})
        if d is None:
            break
        z = z - d
        hits.append(z)
        z -= 40.0
    return hits

def run(start, count):
    s = [7919 + start * 104729]
    def rnd():
        s[0] = (s[0] * 1103515245 + 12345) % 2147483648
        return s[0] / 2147483648.0
    placed = []
    for i in range(start, start + count):
        for _ in range(30):
            x = -TOTAL_HALF + rnd() * 2 * TOTAL_HALF
            y = -TOTAL_HALF + rnd() * 2 * TOTAL_HALF
            hits = ground_z(x, y)
            if hits and abs(hits[0] - hits[-1]) < 150.0:
                break
        else:
            continue
        m = int(rnd() * 11) % 11 + 1
        yaw = rnd() * 360.0
        pitch = -20.0 + rnd() * 40.0
        roll = -20.0 + rnd() * 40.0
        sc = 15.0 + rnd() * 35.0
        ox, oy = OFFSETS[m - 1]
        c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        px = x - sc * (ox * c - oy * sn)
        py = y - sc * (ox * sn + oy * c)
        a = call("add_to_scene_from_asset",
                 asset_path="/Game/Environment/Rocks/SM_Rocks_%02d" % m,
                 name="Rock_%03d" % i,
                 xform={"location": {"x": px, "y": py, "z": hits[-1] - 6.0 * sc},
                        "rotation": {"pitch": pitch, "yaw": yaw, "roll": roll},
                        "scale": {"x": sc, "y": sc, "z": sc}})
        if a:
            call("set_actor_folder", actor=a, folder_path="Environment/Rocks")
            placed.append(i)
    return {"placed": len(placed)}
