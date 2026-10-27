// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
// Model-derived local opaque geometry and deduplicated placed emitters.
#ifndef RT_SCENE_GRID
#define RT_SCENE_GRID
#include "/lib/lighting/SceneShapes.glsl"
#include "/lib/lighting/GlassMaterial.glsl"
const int rtSceneSize = 64;
const uint rtMaxLights = 256u;
#ifdef RT_SCENE_WRITE
layout(r32ui) coherent uniform uimage3D rtSceneGrid;
layout(std430, binding = 5) coherent buffer RTSceneState {
    uint lightCount; uint overflow; uint pad0; uint pad1;
    vec4 lights[256];
} rtScene;

void RTRecordScene(int blockID, vec3 relativeCenter) {
    uint index = RTSceneClass(blockID);
    if (index == 0u || index >= rtSceneClassCount) return;
    ivec3 cell = ivec3(floor(relativeCenter + fract(cameraPosition))) + ivec3(32);
    if (any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, ivec3(64)))) return;
    uint previous = imageAtomicCompSwap(rtSceneGrid, cell, 0u, index);
    uint kind = RTSceneInfo(index).y;
    if (previous == 0u && kind != 0u) {
        uint slot = atomicAdd(rtScene.lightCount, 1u);
        uint packedPosition = texelFetch(rtSceneShapesTex, ivec2(int(index), 0), 0).w;
        vec3 sourcePosition = vec3(packedPosition & 63u, (packedPosition >> 6u) & 63u, (packedPosition >> 12u) & 63u) * (1.0 / 32.0);
        if (slot < rtMaxLights) rtScene.lights[slot] = vec4(vec3(cell) + sourcePosition, float(kind));
        else atomicOr(rtScene.overflow, 1u);
    }
}
#else
uniform usampler3D rtSceneGridTex;
layout(std430, binding = 5) readonly buffer RTSceneState {
    uint lightCount; uint overflow; uint pad0; uint pad1;
    vec4 lights[256];
} rtScene;

vec3 RTGridPosition(vec3 playerPos) { return playerPos + fract(cameraPosition) + vec3(32.0); }

bool RTInsideScene(vec3 p) { return all(greaterThanEqual(p, vec3(0.0))) && all(lessThan(p, vec3(64.0))); }

uniform usampler2D rtSceneAlphaTex;

// DDA at the source texture's 1/16-block scale, only inside cutout blocks.
// Tests real holes instead of treating the panel's bounding box as opaque.
bool RTAlphaShapeHit(uint shape, vec3 origin, vec3 direction, float maxDistance) {
    vec2 span = RTGlassBoxInterval(origin, direction, maxDistance, vec3(0.0), vec3(1.0));
    float t = max(span.x, 0.001) + 1e-5;
    if (span.y <= t) return false;
    ivec3 cell = clamp(ivec3(floor((origin + direction * t) * 16.0)), ivec3(0), ivec3(15));
    ivec3 delta = ivec3(sign(direction));
    vec3 dt, nextT;
    for (int axis = 0; axis < 3; ++axis) {
        if (abs(direction[axis]) < 1e-7) { dt[axis] = 1e20; nextT[axis] = 1e20; }
        else {
            dt[axis] = abs(1.0 / (16.0 * direction[axis]));
            nextT[axis] = (float(cell[axis] + (delta[axis] > 0 ? 1 : 0)) / 16.0 - origin[axis]) / direction[axis];
        }
    }
    for (int i = 0; i < 48; ++i) {
        if (t >= span.y || any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, ivec3(16)))) break;
        uint bit = uint(cell.x + 16 * cell.y + 256 * cell.z);
        uvec4 words = texelFetch(rtSceneAlphaTex, ivec2(int(bit >> 7u), int(shape)), 0);
        if ((words[int((bit >> 5u) & 3u)] & (1u << (bit & 31u))) != 0u) return true;
        t = minOf(nextT);
        for (int axis = 0; axis < 3; ++axis) if (nextT[axis] <= t + 1e-6) { cell[axis] += delta[axis]; nextT[axis] += dt[axis]; }
    }
    return false;
}

bool RTShapeHit(uint shape, vec3 origin, vec3 direction, float maxDistance) {
    if ((shape & 0x80000000u) != 0u) return RTAlphaShapeHit(shape & 0x7fffffffu, origin, direction, maxDistance);
    uvec2 range = RTShapeRange(shape);
    for (uint i = 0u; i < range.y; ++i) {
        uint boxBits = RTShapeBox(range.x + i);
        vec3 lo = vec3(boxBits & 31u, (boxBits >> 5u) & 31u, (boxBits >> 10u) & 31u) * (1.0 / 16.0);
        vec3 hi = vec3((boxBits >> 15u) & 31u, (boxBits >> 20u) & 31u, (boxBits >> 25u) & 31u) * (1.0 / 16.0);
        vec2 interval = RTGlassBoxInterval(origin, direction, maxDistance, lo, hi);
        if (interval.y > max(interval.x, 0.015)) return true;
    }
    return false;
}

// Only opaque model boxes are tested. Glass is accumulated separately with the
// same finite endpoints. The emitting cell is excluded to avoid self-occlusion.
bool RTSceneOccluded(vec3 playerOrigin, vec3 playerTarget) {
    vec3 origin = RTGridPosition(playerOrigin);
    vec3 target = RTGridPosition(playerTarget);
    vec3 delta = target - origin;
    float distanceToLight = length(delta);
    if (distanceToLight < 0.03) return false;
    vec3 direction = delta / distanceToLight;
    float maxDistance = max(distanceToLight - 0.015, 0.0);
    vec2 span = RTGlassBoxInterval(origin, direction, maxDistance, vec3(0.0), vec3(64.0));
    if (span.y <= span.x) return false;
    float t = span.x + 1e-4;
    ivec3 cell = clamp(ivec3(floor(origin + direction * t)), ivec3(0), ivec3(63));
    ivec3 finalCell = ivec3(floor(target));
    ivec3 stepCell = ivec3(sign(direction));
    vec3 stepT, nextT;
    for (int axis = 0; axis < 3; ++axis) {
        if (abs(direction[axis]) < 1e-7) { stepT[axis] = 1e20; nextT[axis] = 1e20; }
        else {
            stepT[axis] = abs(1.0 / direction[axis]);
            nextT[axis] = (float(cell[axis] + (stepCell[axis] > 0 ? 1 : 0)) - origin[axis]) / direction[axis];
        }
    }
    // Bound the DDA by the number of grid planes along this finite segment.
    // A runtime bound keeps the full cutout tracer from being expanded 192
    // times by the driver when it links Iris's combined compute program.
    int stepLimit = min(192, int(ceil((span.y - span.x) * dot(abs(direction), vec3(1.0)))) + 4);
    for (int stepIndex = 0; stepIndex < stepLimit; ++stepIndex) {
        if (t >= span.y || any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, ivec3(64)))) break;
        if (cell != finalCell) {
            uint index = texelFetch(rtSceneGridTex, cell, 0).r;
            if (index > 0u && index < rtSceneClassCount) {
                uint shape = RTSceneInfo(index).x;
                if (shape != 0u && RTShapeHit(shape, origin - vec3(cell), direction, maxDistance)) return true;
            }
        }
        t = minOf(nextT);
        for (int axis = 0; axis < 3; ++axis) if (nextT[axis] <= t + 1e-5) { cell[axis] += stepCell[axis]; nextT[axis] += stepT[axis]; }
    }
    return false;
}
#endif
#endif
