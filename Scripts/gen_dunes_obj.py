"""Dense OBJ of the same terrain_height() used by Scripts/rebuild_terrain.py, with analytic smooth normals."""
import sys
import numpy as np

N = int(sys.argv[1]) if len(sys.argv) > 1 else 512
OUT = sys.argv[2]
SIZE = 64000.0
SPAWN_CLEAR_RADIUS = 4500.0
M32 = 0xFFFFFFFF


def hash2(ix, iy, seed):
    n = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & M32
    n = ((n ^ (n >> 13)) * 1274126177) & M32
    return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0


def value_noise(x, y, seed):
    ix = np.floor(x).astype(np.int64)
    iy = np.floor(y).astype(np.int64)
    tx, ty = x - ix, y - iy
    fx, fy = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a = hash2(ix, iy, seed)
    b = hash2(ix + 1, iy, seed)
    c = hash2(ix, iy + 1, seed)
    d = hash2(ix + 1, iy + 1, seed)
    return (a + (b - a) * fx) + ((c + (d - c) * fx) - (a + (b - a) * fx)) * fy


def height(x, y):
    h = (value_noise(x / 14000.0, y / 14000.0, 11) - 0.5) * 2.0 * 700.0
    h += (value_noise(x / 5200.0, y / 5200.0, 23) - 0.5) * 2.0 * 200.0
    h += (value_noise(x / 30000.0, y / 30000.0, 41) - 0.5) * 2.0 * 1100.0
    h += (value_noise(x / 26000.0, y / 26000.0, 77) - 0.5) * 2.0 * 2500.0
    warp = (value_noise(x / 9000.0, y / 9000.0, 5) - 0.5) * 4.0
    r = np.sin(x * 0.00042 + y * 0.00012 + warp * 2.3) * 140.0
    r += np.sin(x * 0.0011 + y * 0.0004 + warp) * 35.0
    r += np.sin(x * 0.0007 - y * 0.0009 + warp * 1.7) * 30.0
    calm = np.clip(np.hypot(x, y) / SPAWN_CLEAR_RADIUS, 0.35, 1.0)
    return (h + r) * calm


half = SIZE / 2
step = SIZE / N
xs = -half + np.arange(N + 1) * step
X, Y = np.meshgrid(xs, xs)
Z = height(X, Y)
# analytic-ish normals from central differences of the height function
e = step
dzdx = (height(X + e, Y) - height(X - e, Y)) / (2 * e)
dzdy = (height(X, Y + e) - height(X, Y - e)) / (2 * e)
nrm = np.stack([-dzdx, -dzdy, np.ones_like(Z)], axis=-1)
nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)

with open(OUT, "w") as f:
    f.write("o DuneTerrainHD\n")
    np.savetxt(f, np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1), fmt="v %.3f %.3f %.3f")
    np.savetxt(f, nrm.reshape(-1, 3), fmt="vn %.5f %.5f %.5f")
    idx = np.arange((N + 1) * (N + 1)).reshape(N + 1, N + 1) + 1
    a = idx[:-1, :-1].ravel(); b = idx[:-1, 1:].ravel()
    c = idx[1:, :-1].ravel(); d = idx[1:, 1:].ravel()
    t1 = np.stack([a, b, c], axis=1); t2 = np.stack([b, d, c], axis=1)
    tris = np.concatenate([t1, t2])
    np.savetxt(f, tris, fmt="f %d//%d %d//%d %d//%d", header="", comments="") if False else None
    for t in (t1, t2):
        np.savetxt(f, np.stack([t[:, 0], t[:, 0], t[:, 1], t[:, 1], t[:, 2], t[:, 2]], axis=1), fmt="f %d//%d %d//%d %d//%d")
print("verts", (N + 1) ** 2, "tris", 2 * N * N, "z", float(Z.min()), float(Z.max()))
