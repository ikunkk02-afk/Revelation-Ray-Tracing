// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
// Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
// Revelation RT modifications, 2026-10-26. Apache-2.0.
#if !defined INCLUDE_LIB_LIGHTING_SSRT
#define INCLUDE_LIB_LIGHTING_SSRT

// Perspective-correct screen-space ray segments, after McGuire and Mara (2014).
// https://jcgt.org/published/0003/04/04/paper.pdf
#define SSRT_MAX_SAMPLES 24 // [4 8 12 16 24 32 48 64 96 128 256 512]
#define SSRT_REFINEMENT
#define SSRT_REFINEMENT_STEPS 4 // [2 3 4 5 6 8 10 12 16]

bool RTReadDepth(vec2 uv, out float depth) {
	ivec2 texel = clamp(uvToTexelScaled(uv), ivec2(0), ivec2(scaledViewSize) - 1);
	depth = loadDepth2(texel); // Opaque depth without the first-person hand.
#if defined LOD_MOD
	if (depth >= 1.0) {
		float lodDepth = loadDepth1Lod(texel);
		if (lodDepth >= 1.0) return false;
		depth = ViewToScreenDepth(ScreenToViewDepthLod(lodDepth));
		return true;
	}
#endif
	return depth < 1.0;
}

bool TraceScreenRayThickness(vec3 viewOrigin, vec3 viewDir, float dither, uint steps,
	float maxDistance, float hitThickness, out vec3 hitPos) {
	hitPos = vec3(0.0);
	if (steps == 0u || maxDistance <= 0.0 || viewOrigin.z >= -near) return false;
	float dirLength = length(viewDir);
	if (dirLength < 1e-6) return false;
	viewDir /= dirLength;

	float rayLength = maxDistance;
	if (viewDir.z > 1e-6) rayLength = min(rayLength, (-near * 1.01 - viewOrigin.z) / viewDir.z);
	if (rayLength <= 1e-4) return false;
	vec3 start = ViewToScreenPos(viewOrigin);
	vec3 delta = ViewToScreenPos(viewOrigin + viewDir * rayLength) - start;
	if (any(lessThan(start.xy, vec2(0.0))) || any(greaterThanEqual(start.xy, vec2(1.0)))) return false;

	// Clip to the viewport without divisions by zero for axis-parallel rays.
	float endT = 1.0;
	for (int axis = 0; axis < 2; ++axis) {
		if (abs(delta[axis]) > 1e-7) {
			float edge = delta[axis] > 0.0 ? 1.0 - 1e-6 : 1e-6;
			endT = min(endT, (edge - start[axis]) / delta[axis]);
		}
	}
	if (endT <= 0.0) return false;
	delta *= endT;
	float invSteps = 1.0 / float(steps);
	float prevT = 0.0;
	for (uint i = 0u; i < steps; ++i) {
		float t = i + 1u == steps ? 1.0 : (float(i) + mix(0.25, 1.0, saturate(dither))) * invSteps;
		vec3 samplePos = start + delta * t;
		float depth;
		if (RTReadDepth(samplePos.xy, depth)) {
			float surfaceZ = -ScreenToViewDepth(depth);
			float rayZ = -ScreenToViewDepth(samplePos.z);
			float prevZ = -ScreenToViewDepth((start + delta * prevT).z);
			float thickness = hitThickness + surfaceZ * 1e-4;
			if (max(prevZ, rayZ) >= surfaceZ && min(prevZ, rayZ) <= surfaceZ + thickness) {
				float lo = prevT;
				float hi = t;
				bool startsBehind = prevZ >= surfaceZ;
#ifdef SSRT_REFINEMENT
				for (int refine = 0; refine < SSRT_REFINEMENT_STEPS; ++refine) {
					float mid = (lo + hi) * 0.5;
					vec3 p = start + delta * mid;
					float d;
					bool valid = RTReadDepth(p.xy, d);
					bool behind = valid && -ScreenToViewDepth(p.z) >= -ScreenToViewDepth(d);
					if (behind == startsBehind) lo = mid; else hi = mid;
				}
#endif
				vec3 candidate = start + delta * (startsBehind ? lo : hi);
				float candidateDepth;
				if (RTReadDepth(candidate.xy, candidateDepth)) {
					float gap = -ScreenToViewDepth(candidate.z) + ScreenToViewDepth(candidateDepth);
					vec3 surfacePos = ScreenToViewPos(vec3(candidate.xy, candidateDepth));
					if (gap >= -0.002 && gap <= thickness && distance(surfacePos, viewOrigin) > 0.03
						&& distance(surfacePos, viewOrigin) <= maxDistance + thickness) {
						hitPos = vec3(candidate.xy, candidateDepth);
						return true;
					}
				}
			}
		}
		prevT = t;
	}
	return false;
}

bool TraceScreenRay(vec3 viewOrigin, vec3 viewDir, float dither, uint steps,
    float maxDistance, out vec3 hitPos) {
    return TraceScreenRayThickness(viewOrigin, viewDir, dither, steps, maxDistance, RT_HIT_THICKNESS, hitPos);
}

bool ScreenSpaceRaytrace(vec3 viewOrigin, vec3 viewDir, float dither, uint steps, out vec3 hitPos) {
	return TraceScreenRay(viewOrigin, viewDir, dither, steps, RT_MAX_DISTANCE, hitPos);
}

#endif // INCLUDE_LIB_LIGHTING_SSRT
