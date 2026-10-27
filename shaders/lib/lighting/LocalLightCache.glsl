// Revelation RT v7, Apache-2.0. Current-frame irradiance; no temporal trails.
#ifndef RT_LOCAL_LIGHT_CACHE
#define RT_LOCAL_LIGHT_CACHE
#ifdef RT_LOCAL_HALF_RES
#if defined RT_LOCAL_LIGHTS || defined HANDHELD_LIGHTING
#ifdef RT_LOCAL_LIGHTS
#include "/lib/lighting/LightTiles.glsl"
#endif
uniform sampler2D rtLocalDiffuseTex;
uniform sampler2D rtLocalSpecularTex;

bool RTLocalLightingRelevant(ivec2 texel) {
    bool relevant = false;
#ifdef HANDHELD_LIGHTING
    relevant = heldBlockLightValue > 0 || heldBlockLightValue2 > 0;
#endif
#ifdef RT_LOCAL_LIGHTS
    relevant = relevant || RTLocalCovered(texel);
#endif
    return relevant;
}

bool RTGatherLocalDiffuse(ivec2 texel, vec3 viewPos, vec3 worldNormal, Material material,
    out vec3 light, out vec3 specular) {
    light = vec3(0.0);
    specular = vec3(0.0);
    // Empty light tiles need neither reconstruction nor visibility rays.
    if (!RTLocalLightingRelevant(texel)) return true;
    // Narrow mirror lobes and their moving highlights need native shading.
    if (material.specularMask && material.roughness < 0.08) return false;
    vec2 p = (vec2(texel) + 0.5) * 0.5 - 0.75;
    ivec2 base = ivec2(floor(p));
    vec4 weights = bilinear(fract(p));
    float total = 0.0;
    vec3 low = vec3(1e20), high = vec3(0.0);
    vec3 viewNormal = mat3(gbufferModelView) * worldNormal;
    ivec2 end = min(textureSize(rtLocalDiffuseTex, 0), ivec2(scaledHalfViewSize));
    for (uint i = 0u; i < 4u; ++i) {
        ivec2 s = base + offset2x2[i];
        if (any(lessThan(s, ivec2(0))) || any(greaterThanEqual(s, end))) continue;
        vec4 cached = texelFetch(rtLocalDiffuseTex, s, 0);
        if (cached.a >= -1e-5) continue;
        ivec2 full = min(s * 2 + 1, ivec2(scaledViewSize) - 1);
        vec3 normal = FetchSurfaceNormal(full);
        if (dot(normal, worldNormal) < 0.98) continue;
        Material sampleMaterial = GetMaterialData(ExtractSpecularTex(loadMaterialPack(full)), FetchBaseColor(full));
        if (abs(sampleMaterial.roughness - material.roughness) > 0.03 ||
            abs(sampleMaterial.metallic - material.metallic) > 0.01 ||
            maxOf(abs(sampleMaterial.reflectance - material.reflectance)) > 0.02) continue;
        vec3 samplePos = ScreenToViewPos(vec3((vec2(full) + 0.5) * scaledTexelSize, ViewToScreenDepth(cached.a)));
        // Compare positions on the receiver plane, not raw depth on sloped walls.
        float planeDistance = abs(dot(samplePos - viewPos, viewNormal));
        if (planeDistance > 0.02 + abs(viewPos.z) * 0.001) continue;
        float weight = weights[i];
        if (weight <= 0.001) continue;
        low = min(low, cached.rgb); high = max(high, cached.rgb);
        light += cached.rgb * weight;
        specular += texelFetch(rtLocalSpecularTex, s, 0).rgb * weight;
        total += weight;
    }
    // Trace at native resolution at silhouettes, aperture shadows and sharp
    // colour boundaries. This keeps trapdoor holes and stained-glass edges.
    if (total < 0.5 || maxOf(high - low) > max(0.04, maxOf(high) * 0.4)) return false;
    light /= total;
    specular /= total;
    return true;
}
#endif
#endif
#endif
