// Revelation RT v8.3, 2026-10-27. Apache-2.0.
// Analytic importance of one captured emitter at a receiver. Costs a few dozen
// ALU ops and no memory traffic; the ray-traced part costs 20-50x more, so this
// is what a per-pixel trace budget must be spent on.
#ifndef RT_LOCAL_WEIGHT
#define RT_LOCAL_WEIGHT
#include "/lib/lighting/SceneGrid.glsl"
#include "/lib/lighting/Emitters.glsl"

float RTLocalEmitterWeight(uint index, float lightCount, vec3 playerPos, vec3 worldNormal) {
    if (index >= min(lightCount, rtMaxLights)) return 0.0;
    vec4 light = rtScene.lights[index];
    uint kind = uint(light.w + 0.5);
    vec3 delta = light.xyz - fract(cameraPosition) - vec3(32.0) - playerPos;
    float distanceSquared = dot(delta, delta);
    float range = RTEmitterRange(kind);
    float radius = RTEmitterRadius(kind) * RT_LOCAL_SOURCE_SIZE;
    if (distanceSquared >= sqr(range + radius) || distanceSquared < 1e-6) return 0.0;
    float cosReceiver = dot(worldNormal, delta);
    // Reject only when the whole disc is behind the receiver plane.
    if (cosReceiver + radius <= 0.0) return 0.0;
    float NdotL = saturate(cosReceiver * inversesqrt(distanceSquared));
    if (NdotL <= 0.0) return 0.0;
    // Same kernel the tracer will use, so ranking matches the final energy.
    return RTEmitterFlux(kind) * RTFalloff(distanceSquared, range, RTEmitterRadius(kind)) * NdotL;
}
#endif
