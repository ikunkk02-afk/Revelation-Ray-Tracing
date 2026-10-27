// Revelation RT v7.1, Apache-2.0. Resolve two hand proxies once per frame.
#ifndef RT_HANDHELD_POSITION
#define RT_HANDHELD_POSITION
uniform bool isRightHanded;
#ifdef RT_HANDHELD_POSITION_WRITE
layout(std430, binding = 6) writeonly buffer RTHandheldPositions {
    vec4 source[2]; // view-space centre, safe soft-shadow radius
} rtHandheld;
#include "/lib/lighting/GlassMaterial.glsl"
#ifdef RT_SCENE_ENABLED
#include "/lib/lighting/SceneGrid.glsl"
#endif
#ifdef RT_GLASS_ENABLED
#include "/lib/lighting/GlassGrid.glsl"
#endif

float RTHandheldBoxDistance(vec3 origin, vec3 dir, float distance, vec3 lo, vec3 hi, float radius) {
    if (any(lessThanEqual(hi, lo))) return distance;
    vec2 span = RTGlassBoxInterval(origin, dir, distance, lo - radius, hi + radius);
    if (span.x == 0.0) {
        vec2 solid = RTGlassBoxInterval(origin, dir, distance, lo, hi);
        // The eye may already touch the radius envelope of a wall behind it.
        // Moving the source away from that wall must remain possible.
        if (solid.y <= solid.x) return distance;
    }
    return span.y > span.x ? span.x : distance;
}

#ifdef RT_SCENE_ENABLED
float RTHandheldShapeDistance(uint shape, vec3 origin, vec3 dir, float distance, float radius) {
    float closest = distance;
    if ((shape & 0x80000000u) != 0u) {
        // Probe the real alpha volume, including six source-radius offsets.
        // A prefix query is monotonic, so binary search locates first contact
        // even when the endpoint has already passed through a thin trapdoor.
        const vec3 offsets[7] = vec3[7](vec3(0),vec3(1,0,0),vec3(-1,0,0),
            vec3(0,1,0),vec3(0,-1,0),vec3(0,0,1),vec3(0,0,-1));
        for (int probe = 0; probe < 7; ++probe) {
            vec3 p = origin + offsets[probe] * radius;
            if (!RTAlphaShapeHit(shape & 0x7fffffffu, p, dir, closest)) continue;
            float lo = 0.0, hi = closest;
            for (int step = 0; step < 9; ++step) {
                float mid = (lo + hi) * 0.5;
                if (RTAlphaShapeHit(shape & 0x7fffffffu, p, dir, mid)) hi = mid;
                else lo = mid;
            }
            closest = min(closest, lo);
        }
    } else {
        uvec2 range = RTShapeRange(shape);
        for (uint i = 0u; i < range.y; ++i) {
            uint bits = RTShapeBox(range.x + i);
            vec3 lo = vec3(bits & 31u,(bits >> 5u) & 31u,(bits >> 10u) & 31u) / 16.0;
            vec3 hi = vec3((bits >> 15u) & 31u,(bits >> 20u) & 31u,(bits >> 25u) & 31u) / 16.0;
            closest = min(closest, RTHandheldBoxDistance(origin,dir,closest,lo,hi,radius));
        }
    }
    return closest;
}
#endif

vec4 RTResolveHandheldPosition(int hand) {
    float side = (hand == 0) == isRightHanded ? 1.0 : -1.0;
    vec3 desired = vec3(side * 0.35, -0.20, -0.55);
    float radius = RT_HANDHELD_RADIUS;
#if defined RT_SCENE_ENABLED || defined RT_GLASS_ENABLED
    vec3 origin = transMAD(gbufferModelViewInverse, vec3(0.0)) + fract(cameraPosition) + vec3(32.0);
    vec3 target = transMAD(gbufferModelViewInverse, desired) + fract(cameraPosition) + vec3(32.0);
    float distance = length(target - origin);
    vec3 dir = (target - origin) / distance;
    float closest = distance;
    // The <0.7-block proxy plus radius spans at most 3 cells per axis.
    ivec3 first = clamp(ivec3(floor(min(origin,target) - radius)),ivec3(0),ivec3(63));
    ivec3 last = clamp(ivec3(floor(max(origin,target) + radius)),ivec3(0),ivec3(63));
    for (int z = first.z; z <= last.z; ++z)
    for (int y = first.y; y <= last.y; ++y)
    for (int x = first.x; x <= last.x; ++x) {
        ivec3 cell = ivec3(x,y,z);
        vec3 localOrigin = origin - vec3(cell);
#ifdef RT_SCENE_ENABLED
        uint index = texelFetch(rtSceneGridTex,cell,0).r;
        if (index > 0u && index < rtSceneClassCount) {
            uint shape = RTSceneInfo(index).x;
            if (shape != 0u) closest = min(closest,RTHandheldShapeDistance(shape,localOrigin,dir,closest,radius));
        }
#endif
#ifdef RT_GLASS_ENABLED
        uint code = texelFetch(rtGlassGridTex,cell,0).r;
        if (code != 0u) for (int i = 0; i < 5; ++i) {
            vec3 lo,hi; RTGlassBounds(code,i,lo,hi);
            closest = min(closest,RTHandheldBoxDistance(localOrigin,dir,closest,lo,hi,radius));
        }
#endif
    }
    float travel = closest < distance ? max(0.0,closest - 0.015) : distance;
    // Shrink the area source near contact as well, so its samples cannot stay
    // on the far side after the centre has retreated all the way to the eye.
    return vec4(desired * (travel / distance), radius * smoothstep(0.0,0.12,travel));
#else
    // Legacy lighting without captured local geometry uses an eye light.
    return vec4(0.0);
#endif
}
#else
layout(std430, binding = 6) readonly buffer RTHandheldPositions {
    vec4 source[2];
} rtHandheld;
#endif
#endif
