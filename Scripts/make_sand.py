"""Generate tileable high-contrast silver-sand textures (albedo + roughness)."""
import numpy as np
from PIL import Image

N = 2048
rng = np.random.default_rng(7)


def blur(a, sigma):
    """Gaussian blur via FFT (wraps, so the result tiles)."""
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2 * (np.pi ** 2) * (sigma ** 2) * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def norm(a):
    a = a - a.min()
    return a / (a.max() + 1e-9)


grain = rng.random((N, N))                      # per-pixel grains
fine = norm(blur(rng.standard_normal((N, N)), 0.8))   # sub-grain clumping
mid = norm(blur(rng.standard_normal((N, N)), 4.0))
macro = norm(blur(rng.standard_normal((N, N)), 40.0))

# bright silver base with slight low-frequency drift
silver = 0.80 + 0.16 * grain + 0.06 * (mid - 0.5) + 0.05 * (macro - 0.5)
silver = np.clip(silver, 0, 1)

# dark speckles: sparse, high-contrast
speck_field = 0.55 * grain + 0.45 * fine
thr = np.quantile(speck_field, 0.86)
speck = np.clip((thr - speck_field) / 0.06, 0, 1) * 0 + np.clip((speck_field - thr) * -1, 0, 1)
dark_mask = (speck_field < np.quantile(speck_field, 0.14)).astype(np.float64)
dark_mask = blur(dark_mask, 0.6)
dark_mask = np.clip(dark_mask * 1.8, 0, 1)
dark_level = 0.10 + 0.14 * rng.random((N, N))

lum = silver * (1 - dark_mask) + dark_level * dark_mask
lum = np.clip(lum, 0, 1)

# very slight cool tint on the silver
r = lum * 0.99
g = lum * 1.00
b = lum * 1.03
albedo = np.stack([r, g, b], axis=-1)
albedo = np.clip(albedo, 0, 1)

# roughness: bright grains glossy-ish, dark grains matte
bright = norm(lum)
rough = 0.92 - 0.58 * (bright ** 1.5) + 0.05 * (rng.random((N, N)) - 0.5)
rough = np.clip(rough, 0.25, 0.95)

import os
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sand_textures")
os.makedirs(out, exist_ok=True)
Image.fromarray((albedo * 255).astype(np.uint8), "RGB").save(os.path.join(out, "T_SilverSand_D.png"))
Image.fromarray((rough * 255).astype(np.uint8), "L").save(os.path.join(out, "T_SilverSand_R.png"))
print("dark fraction", float(dark_mask.mean()), "lum mean", float(lum.mean()), "rough mean", float(rough.mean()))
