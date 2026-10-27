// Revelation RT v8, 2026-10-27. Apache-2.0.
// All lights affecting the receiver; finite area samples integrate visibility,
// cosine, distance attenuation and GGX at the same point on the source.
#ifndef RT_LOCAL_LIGHTING
#define RT_LOCAL_LIGHTING
// NVIDIA expands the area-light tracer once per loop body. Every loop in this
// header is bounded at runtime, so the driver's unroller only costs compile time
// (tens of seconds of glLinkProgram per program); ask it to stop.
#pragma optionNV(unroll none)
#include "/lib/lighting/SceneGrid.glsl"
#include "/lib/lighting/LightTiles.glsl"
#include "/lib/lighting/Emitters.glsl"
#include "/lib/lighting/LocalWeight.glsl"
#include "/lib/lighting/LocalVisibility.glsl"
#define RT_GOLDEN_ANGLE 2.39996323
#ifndef RT_LOCAL_MAX_TRACED
    #define RT_LOCAL_MAX_TRACED 4
#endif
#ifndef RT_LOCAL_IMPORTANCE_CUTOFF
    #define RT_LOCAL_IMPORTANCE_CUTOFF 0.0
#endif

void RTIntegrateLocalEmitter(uint index, vec3 playerPos, vec3 origin, vec3 worldNormal,
    vec3 viewNormal, vec3 viewDirection, Material material, float dither,
    inout vec3 diffuse, inout vec3 specular) {
    if (index >= min(rtScene.lightCount, rtMaxLights)) return;
    vec4 light = rtScene.lights[index];
    uint kind = uint(light.w + 0.5);
    vec3 lightPos = light.xyz - fract(cameraPosition) - vec3(32.0);
    vec3 delta = lightPos - playerPos;
    float distanceSquared = dot(delta, delta);
    float range = RTEmitterRange(kind);
    float radius = RTEmitterRadius(kind) * RT_LOCAL_SOURCE_SIZE;
    if (distanceSquared >= sqr(range + radius) || distanceSquared < 1e-6) return;
    vec3 worldL = delta * inversesqrt(distanceSquared);
    // The whole emitting disc must be behind the receiver before rejecting it.
    if (dot(worldNormal, delta) + radius <= 0.0) return;
#ifndef RT_LOCAL_SOFT_SHADOWS
    // Stable single-centre projection. Sparse area taps are separate virtual
    // lamps: through a trapdoor they produce several displaced copies of every
    // aperture. Quality presets use this one-source approximation instead.
    float NdotL = saturate(dot(worldNormal, worldL));
    if (NdotL <= 0.0 || distanceSquared >= range * range) return;
    vec3 visibility = vec3(1.0);
#ifdef RT_LOCAL_TRACED_SHADOWS
    visibility = RTTraceLocalVisibility(origin, lightPos);
    if (maxOf(visibility) <= 0.0) return;
#endif
    vec3 incident = RTEmitterColor(kind) * RTFalloff(distanceSquared, range, RTEmitterRadius(kind)) * visibility;
    diffuse += incident * NdotL;
    if (material.specularMask) {
        vec3 L = mat3(gbufferModelView) * worldL;
        vec3 H = L + viewDirection;
        if (dot(H,H) > 1e-8) {
            H = normalize(H);
            specular += incident * RT_LOCAL_SPECULAR * NdotL * SpecularGGX(saturate(dot(viewDirection,H)),
                max(dot(viewNormal,viewDirection),1e-4), NdotL, saturate(dot(viewNormal,H)),
                max(material.roughness,0.02),material.reflectance);
        }
    }
#else
    vec3 up = abs(worldL.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 tangent = normalize(cross(up, worldL));
    vec3 bitangent = cross(worldL, tangent);
    int sampleCount = 1;
#ifdef RT_LOCAL_SOFT_SHADOWS
    sampleCount = max(RT_LOCAL_SHADOW_SAMPLES, 1);
#endif
    // Absolute source position decorrelates adjacent lamps without depending on
    // nondeterministic SSBO insertion order or the camera's current grid origin.
    float rotation = fract(dot(floor(lightPos + cameraPosition), vec3(0.754877666, 0.569840296, 0.438579021)));
#if defined RT_LOCAL_TEMPORAL_SHADOWS && defined RT_LOCAL_SOFT_SHADOWS
    // Optional stochastic mode. The direct-light cache has no dedicated temporal
    // denoiser (SVGF only filters indirect light), so quality presets use the
    // deterministic disc quadrature below instead of relying on final TAA.
    sampleCount = 1;
    float seqFrame = float(frameCounter & 63);
    float seqRadius = sqrt(fract(dither + seqFrame * 0.6180339887 + rotation));
    float seqAngle = rotation * 6.2831853 + seqFrame * RT_GOLDEN_ANGLE;
    vec2 temporalDisk = vec2(cos(seqAngle), sin(seqAngle)) * seqRadius * radius;
#endif
    vec3 color = RTEmitterColor(kind) / float(sampleCount);
    for (int sampleIndex = 0; sampleIndex < sampleCount; ++sampleIndex) {
        float angle = RT_GOLDEN_ANGLE * float(sampleIndex) + rotation * 6.2831853;
        // Midpoints in equal-area annuli: fixed for every pixel and frame.
        // Randomising the radius/rotation made static penumbrae look like sand.
        float radiusScale = sqrt((float(sampleIndex) + 0.5) / float(sampleCount));
        vec2 disk = sampleCount > 1 ? vec2(cos(angle), sin(angle)) * radiusScale * radius : vec2(0.0);
#if defined RT_LOCAL_TEMPORAL_SHADOWS && defined RT_LOCAL_SOFT_SHADOWS
        disk = temporalDisk;
#endif
        vec3 target = lightPos + tangent * disk.x + bitangent * disk.y;
        vec3 sampleDelta = target - playerPos;
        float sampleDist2 = max(dot(sampleDelta, sampleDelta), 1e-6);
        vec3 sampleL = sampleDelta * inversesqrt(sampleDist2);
        float NdotL = saturate(dot(worldNormal, sampleL));
        if (NdotL <= 0.0 || sampleDist2 >= range * range) continue;
        vec3 visibility = vec3(1.0);
#ifdef RT_LOCAL_TRACED_SHADOWS
        visibility = RTTraceLocalVisibility(origin,target);
        if (maxOf(visibility) <= 0.0) continue;
#endif
        vec3 incident = color * RTFalloff(sampleDist2, range, RTEmitterRadius(kind)) * visibility;
        diffuse += incident * NdotL;
        if (material.specularMask) {
            vec3 L = mat3(gbufferModelView) * sampleL;
            vec3 H = L + viewDirection;
            if (dot(H, H) < 1e-8) continue;
            H = normalize(H);
            specular += incident * RT_LOCAL_SPECULAR * NdotL * SpecularGGX(saturate(dot(viewDirection, H)),
                max(dot(viewNormal, viewDirection), 1e-4), NdotL, saturate(dot(viewNormal, H)),
                max(material.roughness, 0.02), material.reflectance);
        }
    }
#endif
}

void AddTracedLocalLighting(vec3 viewPos, vec3 worldNormal, vec3 geometryNormal, Material material,
    bool handMask, float dither, ivec2 texel, inout vec3 diffuse, inout vec3 specular) {
    if (BLOCKLIGHT_BRIGHTNESS <= 0.0 || RT_LOCAL_BRIGHTNESS <= 0.0) return;
    if (handMask) return;
    vec3 playerPos = transMAD(gbufferModelViewInverse, viewPos);
    vec3 origin = playerPos + geometryNormal * max(0.008, abs(viewPos.z) * 8e-5);
    vec3 viewDirection = normalize(-viewPos);
    vec3 viewNormal = mat3(gbufferModelView) * worldNormal;
    uvec4 low = RTLightMask(texel, 0), high = RTLightMask(texel, 1);
    uint lightCount = min(rtScene.lightCount, rtMaxLights);
    // All intersecting lights contribute, including in the traced path.
    // No hard rank cut: a fifth lamp must not disappear as the camera moves.

    for (uint index = 0u; index < lightCount; ++index) {
        uint wordIndex = index >> 5u;
        uint bits = wordIndex < 4u ? low[int(wordIndex)] : high[int(wordIndex - 4u)];
        if ((bits & (1u << (index & 31u))) == 0u) continue;
        RTIntegrateLocalEmitter(index, playerPos, origin, worldNormal, viewNormal, viewDirection, material, dither, diffuse, specular);
    }

}
#endif
