// Revelation RT v8, 2026-10-27. Apache-2.0.
#ifndef RT_LOCAL_VOLUMETRICS_LIBRARY
#define RT_LOCAL_VOLUMETRICS_LIBRARY
#include "/lib/lighting/LocalVisibility.glsl"
#include "/lib/lighting/LightTiles.glsl"
#include "/lib/lighting/Emitters.glsl"
#include "/lib/lighting/LocalWeight.glsl"
#ifndef RT_LOCAL_VOLUME_LIGHT_CAP
    #define RT_LOCAL_VOLUME_LIGHT_CAP 1
#endif
#ifndef RT_LOCAL_IMPORTANCE_CUTOFF
    #define RT_LOCAL_IMPORTANCE_CUTOFF 0.0
#endif
#ifdef RT_LOCAL_VOLUMETRICS
mat2x3 RTRaymarchLocalFog(vec3 rayStart,vec3 rayEnd,float dither,ivec2 fullPixel) {
    if (RT_LOCAL_HAZE_DENSITY <= 0.0) return mat2x3(vec3(0.0),vec3(1.0));
    vec3 ray = rayEnd - rayStart;
    float rayLength = min(length(ray),16.0);
    if (rayLength < 0.01) return mat2x3(vec3(0.0),vec3(1.0));
    vec3 transmittance = vec3(exp(-RT_LOCAL_HAZE_DENSITY * rayLength));
    // Air extinction is independent of lamp count. Culling the last candidate
    // must not abruptly remove the medium at a tile boundary.
    if (rtScene.lightCount == 0u || !RTLocalCovered(fullPixel)) return mat2x3(vec3(0.0),transmittance);
    vec3 rayDir = normalize(ray);
    vec3 scattering = vec3(0.0);
    float stepLength = rayLength / float(RT_LOCAL_VOLUME_SAMPLES);
    // Apply each segment's exact extinction once, and include every candidate
    // light in in-scattering. Nearest-light switching used to cut beams at tiles.
    float segmentScatter = 1.0 - exp(-RT_LOCAL_HAZE_DENSITY * stepLength);
    // A medium has no receiver normal. Surface cosine ranking used to discard
    // lamps behind the march direction and a hard top-N cut lost beam energy.
    // This optional effect integrates all masked lamps; it is off by default.
    uvec4 low = RTLightMask(fullPixel, 0), high = RTLightMask(fullPixel, 1);
    uint lightCount = min(rtScene.lightCount, rtMaxLights);
    for (uint index = 0u; index < lightCount; ++index) {
        uint wordIndex = index >> 5u;
        uint bits = wordIndex < 4u ? low[int(wordIndex)] : high[int(wordIndex - 4u)];
        if ((bits & (1u << (index & 31u))) == 0u) continue;
        vec4 source = rtScene.lights[index];
        uint kind = uint(source.w + 0.5);
        vec3 lightPos = source.xyz - fract(cameraPosition) - vec3(32.0);
        float range = RTEmitterRange(kind);
        for (int i = 0; i < RT_LOCAL_VOLUME_SAMPLES; ++i) {
            float t = (float(i) + dither) * stepLength;
            vec3 p = rayStart + rayDir * t;
            vec3 delta = lightPos - p;
            float distanceSquared = dot(delta,delta);
            if (distanceSquared >= range * range || distanceSquared < 0.0025) continue;
            vec3 visibility = vec3(1.0);
#ifdef RT_LOCAL_TRACED_SHADOWS
            visibility = RTTraceLocalVisibility(p,lightPos);
            if (maxOf(visibility) < 0.002) continue;
#endif
            vec3 L = delta * inversesqrt(distanceSquared);
            const float g = 0.2;
            float denominator = max(1.0 + g*g - 2.0*g*dot(-rayDir,L),0.01);
            float phase = (1.0-g*g)*rPI*0.25*inversesqrt(denominator)/denominator;
            float weight = exp(-RT_LOCAL_HAZE_DENSITY * float(i) * stepLength) * segmentScatter;
            // Light also loses energy on its path from source to medium.
            float sourceTransmission = exp(-RT_LOCAL_HAZE_DENSITY * sqrt(distanceSquared));
            scattering += RTEmitterColor(kind) * RTFalloff(distanceSquared,range,RTEmitterRadius(kind)) * visibility * (weight * phase * sourceTransmission);
        }
    }
    return mat2x3(scattering,transmittance);
}
#endif
#endif
