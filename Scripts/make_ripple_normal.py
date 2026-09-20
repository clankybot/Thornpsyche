"""Tileable wind-swept sand ripple normal map (long parallel ridges with wobble + fine grain)."""
import os
import numpy as np
from PIL import Image

N = 2048
rng = np.random.default_rng(11)


def blur(a, sigma):
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2 * (np.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


yy, xx = np.mgrid[0:N, 0:N] / float(N)
warp = blur(rng.standard_normal((N, N)), 30.0)
warp = warp / np.abs(warp).max()
warp2 = blur(rng.standard_normal((N, N)), 8.0)
warp2 = warp2 / np.abs(warp2).max()

# ridges run along x; integer frequencies keep the tile seamless
ridges = np.sin(2 * np.pi * (24 * yy + 0.6 * warp + 0.15 * warp2))
ridges += 0.45 * np.sin(2 * np.pi * (57 * yy + 1.4 * warp2 + 2 * xx * 0))
grain = blur(rng.standard_normal((N, N)), 0.9)
grain = grain / np.abs(grain).max()
height = ridges + 0.35 * grain

# height -> normal (central differences, wrapped)
dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
strength = 4.0
nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(height)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
nx, ny, nz = nx / ln, ny / ln, nz / ln
rgb = np.stack([nx * 0.5 + 0.5, ny * 0.5 + 0.5, nz * 0.5 + 0.5], axis=-1)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sand_textures")
os.makedirs(out, exist_ok=True)
Image.fromarray((rgb * 255).astype(np.uint8), "RGB").save(os.path.join(out, "T_SandRipple_N.png"))
print("ok", float(nz.mean()))
