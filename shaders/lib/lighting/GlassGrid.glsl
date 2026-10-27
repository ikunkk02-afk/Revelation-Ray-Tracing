/* Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
 * Frame-local 64^3 transmission grid, centered on the camera's integer cell.
 */
#ifndef INCLUDE_LIB_LIGHTING_GLASS_GRID
#define INCLUDE_LIB_LIGHTING_GLASS_GRID
#include "/lib/lighting/GlassMaterial.glsl"

const int rtGlassGridSize = 64;

#ifdef RT_GLASS_WRITE
layout(r32ui) coherent uniform uimage3D rtGlassGrid;
layout(std430, binding = 4) coherent buffer RTGlassState { uint occupiedFlag; } rtGlassState;

void RTRecordGlass(int blockID, vec3 relativeCenter) {
	uint code = RTGlassCode(blockID);
	if (code == 0u) return;
	ivec3 cell = ivec3(floor(relativeCenter + fract(cameraPosition))) + ivec3(rtGlassGridSize / 2);
	if (any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, ivec3(rtGlassGridSize)))) return;
	imageAtomicMax(rtGlassGrid, cell, code);
	atomicOr(rtGlassState.occupiedFlag, 1u);
}
#else
uniform usampler3D rtGlassGridTex;
layout(std430, binding = 4) readonly buffer RTGlassState { uint occupiedFlag; } rtGlassState;

vec3 RTTraceGlass(vec3 viewOrigin, vec3 viewTarget) {
	if (rtGlassState.occupiedFlag == 0u) return vec3(1.0);
	vec3 worldOrigin = transMAD(gbufferModelViewInverse, viewOrigin);
	vec3 worldTarget = transMAD(gbufferModelViewInverse, viewTarget);
	vec3 ray = worldTarget - worldOrigin;
	float rayLength = length(ray);
	if (rayLength < 1e-5) return vec3(1.0);
	vec3 direction = ray / rayLength;
	vec3 origin = worldOrigin + fract(cameraPosition) + vec3(rtGlassGridSize / 2);
	vec2 gridSpan = RTGlassBoxInterval(origin, direction, rayLength, vec3(0.0), vec3(rtGlassGridSize));
	if (gridSpan.y <= gridSpan.x) return vec3(1.0);
	float t = gridSpan.x + 1e-4;
	ivec3 cell = clamp(ivec3(floor(origin + direction * t)), ivec3(0), ivec3(rtGlassGridSize - 1));
	ivec3 cellStep = ivec3(sign(direction));
	vec3 dt;
	vec3 nextT;
	for (int axis = 0; axis < 3; ++axis) {
		if (abs(direction[axis]) < 1e-7) {
			dt[axis] = 1e20;
			nextT[axis] = 1e20;
		} else {
			dt[axis] = abs(1.0 / direction[axis]);
			float boundary = float(cell[axis] + (cellStep[axis] > 0 ? 1 : 0));
			nextT[axis] = (boundary - origin[axis]) / direction[axis];
		}
	}
	vec3 opticalDepth = vec3(0.0);
	// The maximum diagonal across a 64^3 grid visits fewer than 192 cells.
	for (int i = 0; i < 192; ++i) {
		if (t >= gridSpan.y || any(lessThan(cell, ivec3(0))) || any(greaterThanEqual(cell, ivec3(rtGlassGridSize)))) break;
		uint code = texelFetch(rtGlassGridTex, cell, 0).r;
		if (code != 0u) {
			float thickness = RTGlassPathLength(code, origin - vec3(cell), direction, rayLength);
			opticalDepth += RTGlassAbsorptionCoefficient(code) * (thickness * RT_GLASS_DENSITY);
			if (minOf(opticalDepth) > 6.215) return vec3(0.0);
		}
		t = minOf(nextT);
		// Advance all tied axes to avoid double-counting faces and edges.
		for (int axis = 0; axis < 3; ++axis) {
			if (nextT[axis] <= t + 1e-5) {
				cell[axis] += cellStep[axis];
				nextT[axis] += dt[axis];
			}
		}
	}
	return exp(-opticalDepth);
}

// The solar atlas stores the nearest translucent layer. Replace that layer's
// tint only when it lies in the captured grid, then accumulate all local layers.
// Retain the atlas fallback for distant glass and other translucent materials.
bool RTSolarGlassCaptured(vec3 playerPos, float receiverDepth, float glassDepth) {
    if (rtGlassState.occupiedFlag == 0u) return false;
    float distanceToGlass = abs((receiverDepth - glassDepth) * shadowProjectionInverse[2].z * 10.0);
    vec3 p = playerPos + shadowDirWorld * distanceToGlass + fract(cameraPosition) + vec3(32.0);
    return all(greaterThan(p, vec3(0.25))) && all(lessThan(p, vec3(63.75)));
}

vec3 RTSolarGlassTransmission(vec3 playerPos) {
    return RTTraceGlass(transMAD(gbufferModelView, playerPos), transMAD(gbufferModelView, playerPos + shadowDirWorld * 128.0));
}
#endif
#endif
