// Revelation RT v8.3, 2026-10-27. Apache-2.0. Physical emitter model.
#ifndef RT_EMITTERS
#define RT_EMITTERS
#include "/lib/lighting/LightSourceControls.glsl"

// Planckian locus chromaticity (Kim et al. 2002 fit), normalised to unit peak.
// Colour temperature is the only free parameter, exactly like a real fixture's
// rating; the flux in RTEmitterColor sets the magnitude.
vec3 RTBlackbodyChroma(float kelvin) {
    float t = clamp(kelvin, 1000.0, 15000.0);
    float t2 = t * t, t3 = t2 * t;
    float x = t <= 4000.0
        ? -0.2661239e9 / t3 - 0.2343589e6 / t2 + 0.8776956e3 / t + 0.179910
        : -3.0258469e9 / t3 + 2.1070379e6 / t2 + 0.2226347e3 / t + 0.240390;
    float x2 = x * x, x3 = x2 * x;
    float y = t <= 2222.0
        ? -1.1063814 * x3 - 1.34811020 * x2 + 2.18555832 * x - 0.20219683
        : t <= 4000.0
        ? -0.9549476 * x3 - 1.37418593 * x2 + 2.09137015 * x - 0.16748867
        :  3.0817580 * x3 - 5.87338670 * x2 + 3.75112997 * x - 0.37001483;
    vec3 xyz = vec3(x / y, 1.0, (1.0 - x - y) / y);
    vec3 rgb = vec3(dot(xyz, vec3( 3.2404542, -1.5371385, -0.4985314)),
                    dot(xyz, vec3(-0.9692660,  1.8760108,  0.0415560)),
                    dot(xyz, vec3( 0.0556434, -0.2040259,  1.0572252)));
    rgb = max(rgb, vec3(0.0));
    return rgb / max(maxOf(rgb), 1e-5);
}

// Emitted colour and flux per emitter class. Thermal sources are black bodies at
// their real burning temperature; luminous blocks that are not thermal keep the
// measured spectral tint of the block (soul fire, redstone).
// Flux keeps the pack's previous relative brightness, so the look does not jump —
// only the spectral distribution becomes physical.
float RTEmitterFlux(uint kind) {
    if (kind == 2u || kind == 8u || kind == 10u) return 3.1;
    if (kind == 3u) return 1.2;
    if (kind == 5u || kind == 11u) return 3.2;
    if (kind == 6u || kind == 9u) return 3.4;
    if (kind == 12u) return 3.4;
    if (kind == 7u) return 3.4;
    if (kind == 4u) return 3.6;
    if (kind == 1u) return 3.4;
    return 3.4;
}

vec3 RTEmitterColor(uint kind) {
    vec3 chroma;
    float flux = RTEmitterFlux(kind);
    if (kind == 2u || kind == 8u || kind == 10u) { chroma = vec3(0.12, 0.75, 1.0); }
    else if (kind == 3u) { chroma = vec3(1.0, 0.03, 0.01); }
    else if (kind == 5u || kind == 11u) { chroma = vec3(1.000000000, 0.860180811, 0.779364144) /* 5600 K */; }
    else if (kind == 6u || kind == 9u) { chroma = vec3(1.000000000, 0.140372319, 0.000000000) /* 1500 K */; }
    else if (kind == 12u) { chroma = vec3(1.000000000, 0.587986408, 0.281684022) /* 3600 K */; }
    else if (kind == 7u) { chroma = vec3(1.000000000, 0.304470796, 0.028428429) /* 2200 K */; }
    else if (kind == 4u) { chroma = vec3(1.000000000, 0.478525614, 0.154316743) /* 3000 K */; }
    else if (kind == 1u) { chroma = vec3(1.000000000, 0.231706843, 0.000000000) /* 1900 K */; }
    else {
        // The user's blocklight colour control keeps its own tint and brightness.
        chroma = vec3(1.0, 0.65, 0.25);
    }
    return RTBlockLightChroma(chroma) * sRGB_2_Rec2020 * flux;
}

float RTEmitterRadius(uint kind) {
    if (kind <= 3u) return 0.035;
    if (kind == 7u || kind == 8u) return 0.10;
    if (kind == 9u || kind == 10u) return 0.22;
    if (kind == 11u) return 0.04;
    return 0.30;
}
float RTEmitterRange(uint kind) {
    if (kind == 3u) return 7.0;
    if (kind == 2u || kind == 8u || kind == 10u) return 10.0;
    return 15.0;
}

// Radiant kernel of a finite Lambertian disc of radius `radius` carrying the flux
// returned by RTEmitterColor:
//   L     = flux / (pi^2 r^2)      emitted radiance
//   Omega = pi r^2 cos_s / d^2     solid angle the receiver subtends the disc
//   E     = L * Omega * cos_r      irradiance
// => kernel = cos_s * cos_r / (pi * max(d^2, r^2)). cos_r is applied by the
// caller as N.L, so only 1/(pi d^2) lives here. Clamping d^2 at r^2 is what
// keeps a pixel inside the lamp finite instead of diverging, and it is also the
// correct far-field limit of a finite source.
// The finite support window exists so a room full of lamps stays affordable; it
// is continuous and its value and slope both reach zero at the emitter's range,
// so it cannot paint an edge into the shading.
float RTFalloff(float distanceSquared, float range, float radius) {
    float d2 = max(distanceSquared, radius * radius);
    float window = saturate(1.0 - sqr(d2 / (range * range)));
    return RT_LOCAL_BRIGHTNESS * BLOCKLIGHT_BRIGHTNESS * window * window * rPI * rcp(d2);
}
#endif
