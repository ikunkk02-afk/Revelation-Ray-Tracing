/* Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
 * Optical tints and exact vanilla full-block / connected-pane bounds.
 */
#ifndef INCLUDE_LIB_LIGHTING_GLASS_MATERIAL
#define INCLUDE_LIB_LIGHTING_GLASS_MATERIAL

uint RTGlassCode(int blockID) {
	if (blockID >= 13001 && blockID <= 13017) return uint(blockID - 13000);
	if (blockID >= 14000 && blockID < 14272) {
		uint index = uint(blockID - 14000);
		return (index / 16u + 1u) | 32u | ((index & 15u) << 6u);
	}
	return 0u;
}

// Optical density is interpolated in absorption space: adding glass removes
// wavelengths rather than mixing a neutral white floor into every dyed block.
vec3 RTGlassAbsorptionCoefficient(uint code) {
    uint dye = code & 31u;
    const float clearSigma = 0.015113638;
    if (dye == 0u || dye == 17u) return vec3(clearSigma);
    const vec3 sigma[16] = vec3[16](
        vec3(0.116437477,0.116558057,0.116581394),
        vec3(0.375924957,1.454177352,3.255780881),
        vec3(0.747649934,2.395544287,0.587734558),
        vec3(1.440429372,0.847748346,0.065932430),
        vec3(0.141339031,0.301276104,2.379785982),
        vec3(0.901200368,0.300664066,2.463574453),
        vec3(0.343051215,1.370901834,0.922268715),
        vec3(2.297691285,2.297811865,2.297835202),
        vec3(0.867331048,0.867451628,0.867474965),
        vec3(1.680289158,0.808293497,0.592387836),
        vec3(1.612691383,3.179267611,0.522110158),
        vec3(2.752762821,2.850382936,0.220952089),
        vec3(1.896258057,2.618729388,3.864522224),
        vec3(2.070660637,1.219667088,3.281937879),
        vec3(0.574201187,2.605720968,3.808213489),
        vec3(4.311533909,4.311654488,4.311677826));
    return mix(vec3(clearSigma), sigma[min(dye - 1u, 15u)], RT_GLASS_COLOR_STRENGTH);
}
vec3 RTGlassUnitTransmission(uint code) {
    return exp(-RTGlassAbsorptionCoefficient(code));
}
// Bulk absorption per metre; panes retain their actual shorter optical path.
vec3 RTGlassAbsorption(uint code, float pathLength) {
    return exp(-RTGlassAbsorptionCoefficient(code) * (max(pathLength, 0.0) * RT_GLASS_DENSITY));
}

float RTDielectricFresnel(float cosine, float ior) {
    cosine = clamp(abs(cosine), 0.0, 1.0);
    ior = max(ior, 1e-4);
    if (abs(ior - 1.0) < 1e-6) return 0.0;
    float sinT2 = (1.0 - cosine * cosine) / (ior * ior);
    if (sinT2 >= 1.0) return 1.0;
    float cosT = sqrt(max(0.0, 1.0 - sinT2));
    float rs = (cosine - ior * cosT) / max(cosine + ior * cosT, 1e-6);
    float rp = (ior * cosine - cosT) / max(ior * cosine + cosT, 1e-6);
    return clamp(0.5 * (rs * rs + rp * rp), 0.0, 1.0);
}

vec2 RTGlassBoxInterval(vec3 origin, vec3 direction, float rayLength, vec3 boxMin, vec3 boxMax) {
	float lo = 0.0;
	float hi = rayLength;
	for (int axis = 0; axis < 3; ++axis) {
		if (abs(direction[axis]) < 1e-7) {
			if (origin[axis] < boxMin[axis] || origin[axis] > boxMax[axis]) return vec2(0.0);
		} else {
			vec2 t = (vec2(boxMin[axis], boxMax[axis]) - origin[axis]) / direction[axis];
			lo = max(lo, min(t.x, t.y));
			hi = min(hi, max(t.x, t.y));
		}
	}
	return vec2(lo, max(lo, hi));
}

float RTGlassPathLength(uint code, vec3 cellOrigin, vec3 direction, float rayLength) {
	if ((code & 32u) == 0u) {
		vec2 span = RTGlassBoxInterval(cellOrigin, direction, rayLength, vec3(0.0), vec3(1.0));
		return span.y - span.x;
	}
	// Panes: central 2/16 post and up to four connected arms, not a solid cube.
	vec2 spans[5];
	spans[0] = RTGlassBoxInterval(cellOrigin, direction, rayLength, vec3(0.4375,0.0,0.4375), vec3(0.5625,1.0,0.5625));
	uint mask = code >> 6u;
	spans[1] = (mask & 1u) != 0u ? RTGlassBoxInterval(cellOrigin,direction,rayLength,vec3(0.4375,0.0,0.0),vec3(0.5625,1.0,0.5)) : vec2(0.0);
	spans[2] = (mask & 2u) != 0u ? RTGlassBoxInterval(cellOrigin,direction,rayLength,vec3(0.5,0.0,0.4375),vec3(1.0,1.0,0.5625)) : vec2(0.0);
	spans[3] = (mask & 4u) != 0u ? RTGlassBoxInterval(cellOrigin,direction,rayLength,vec3(0.4375,0.0,0.5),vec3(0.5625,1.0,1.0)) : vec2(0.0);
	spans[4] = (mask & 8u) != 0u ? RTGlassBoxInterval(cellOrigin,direction,rayLength,vec3(0.0,0.0,0.4375),vec3(0.5,1.0,0.5625)) : vec2(0.0);
	for (int i = 1; i < 5; ++i) {
		vec2 span = spans[i];
		int j = i - 1;
		while (j >= 0 && spans[j].x > span.x) { spans[j + 1] = spans[j]; --j; }
		spans[j + 1] = span;
	}
	float total = 0.0;
	float end = 0.0;
	for (int i = 0; i < 5; ++i) {
		total += max(0.0, spans[i].y - max(end, spans[i].x));
		end = max(end, spans[i].y);
	}
	return total;
}

void RTGlassBounds(uint code, int i, out vec3 lo, out vec3 hi) {
    lo = vec3(0.0); hi = vec3(1.0);
    if ((code & 32u) == 0u) return;
    lo = vec3(0.4375, 0.0, 0.4375); hi = vec3(0.5625, 1.0, 0.5625);
    uint mask = code >> 6u;
    if (i > 0 && (mask & (1u << uint(i - 1))) == 0u) { hi = lo; return; }
    if (i == 1) { lo.z = 0.0; hi.z = 0.5; }
    if (i == 2) { lo.x = 0.5; hi.x = 1.0; }
    if (i == 3) { lo.z = 0.5; hi.z = 1.0; }
    if (i == 4) { lo.x = 0.0; hi.x = 0.5; }
}

// Exit of the first connected solid segment, including unions of pane arms.
vec2 RTGlassFirstSegment(uint code, vec3 origin, vec3 direction, out vec3 exitNormal) {
    vec2 intervals[5];
    vec3 normals[5];
    int count = (code & 32u) == 0u ? 1 : 5;
    for (int i = 0; i < count; ++i) {
        vec3 lo, hi;
        RTGlassBounds(code, i, lo, hi);
        vec2 span = RTGlassBoxInterval(origin, direction, 4.0, lo, hi);
        if (any(lessThanEqual(hi, lo)) || span.y <= span.x) span = vec2(1e10);
        vec3 exitPoint = origin + direction * min(span.y, 4.0);
        vec3 error = abs(exitPoint - mix(lo, hi, greaterThan(direction, vec3(0.0))));
        for (int axis = 0; axis < 3; ++axis) if (abs(direction[axis]) < 1e-7) error[axis] = 1e10;
        int axis = error.x < error.y ? (error.x < error.z ? 0 : 2) : (error.y < error.z ? 1 : 2);
        normals[i] = vec3(0.0); normals[i][axis] = sign(direction[axis]);
        intervals[i] = span;
    }
    for (int i = 1; i < count; ++i) {
        vec2 span = intervals[i]; vec3 normal = normals[i]; int j = i - 1;
        while (j >= 0 && intervals[j].x > span.x) { intervals[j + 1] = intervals[j]; normals[j + 1] = normals[j]; --j; }
        intervals[j + 1] = span; normals[j + 1] = normal;
    }
    vec2 first = intervals[0]; exitNormal = normals[0];
    for (int i = 1; i < count; ++i) {
        if (intervals[i].x > first.y + 1e-5) break;
        if (intervals[i].y > first.y) { first.y = intervals[i].y; exitNormal = normals[i]; }
    }
    return first.x < 4.0 ? first : vec2(0.0);
}

#endif
