// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
/* Revelation RT modifications, 2026-10-26. Apache-2.0.
 * v2: deterministic contact shadows and nearby stained-glass transmission.
 * Source positions approximate the hands; they do not track animated item meshes.
 */
#ifndef INCLUDE_LIB_LIGHTING_HANDHELD_TRACING
#define INCLUDE_LIB_LIGHTING_HANDHELD_TRACING

#include "/lib/lighting/SSRT.glsl"
#include "/lib/universal/MonteCarlo.glsl"
#if defined RT_HANDHELD_SHADOWS || defined RT_GLASS_ENABLED
#include "/lib/lighting/LocalVisibility.glsl"
#endif
#ifdef RT_GLASS_ENABLED
#include "/lib/lighting/GlassGrid.glsl"
#endif

#ifdef RT_HANDHELD_SHADOWS
#include "/lib/lighting/SceneGrid.glsl"
#endif
uniform bool isRightHanded;

vec3 RTHeldColor(int itemID) {
	// Known emitters retain their intended color even when the item is hidden.
	if (itemID == 10001) return vec3(1.0, 0.60, 0.22) * sRGB_2_Rec2020;
	if (itemID == 10002) return vec3(0.12, 0.75, 1.0) * sRGB_2_Rec2020;
	if (itemID == 10003) return vec3(1.0, 0.03, 0.01) * sRGB_2_Rec2020;
	if (itemID == 10004) return vec3(0.75, 0.95, 1.0) * sRGB_2_Rec2020;
#ifdef COLORED_HANDHELD_LIGHTING
	return mix(vec3(BLOCKLIGHT_COLOR_R, BLOCKLIGHT_COLOR_G, BLOCKLIGHT_COLOR_B) * sRGB_2_Rec2020, handheldAlbedo.average.rgb, handheldAlbedo.average.a);
#else
	return vec3(BLOCKLIGHT_COLOR_R, BLOCKLIGHT_COLOR_G, BLOCKLIGHT_COLOR_B) * sRGB_2_Rec2020;
#endif
}

void AddTracedHandheldLighting(vec3 viewPos, vec3 worldNormal, vec3 geometryNormal, Material material,
	bool handMask, float dither, ivec2 texel, inout vec3 diffuse, inout vec3 specular) {
	vec3 viewNormal = mat3(gbufferModelView) * worldNormal;
	vec3 viewGeoNormal = mat3(gbufferModelView) * geometryNormal;
	vec3 viewDir = normalize(-viewPos);
	for (int hand = 0; hand < 2; ++hand) {
		int level = hand == 0 ? heldBlockLightValue : heldBlockLightValue2;
		if (level <= 0) continue;
		int itemID = hand == 0 ? heldItemId : heldItemId2;
		float side = (hand == 0) == isRightHanded ? 1.0 : -1.0;
		vec3 lightPos = vec3(side * 0.35, -0.20, -0.55);
		vec3 toLight = lightPos - viewPos;
		float dist2 = dot(toLight, toLight);
		float dist = sqrt(max(dist2, 1e-6));
		float range = max(float(level), 2.0);
		if (dist >= range) continue;
		vec3 lightDir = toLight / dist;
		float NdotL = saturate(dot(viewNormal, lightDir));
		if (NdotL <= 0.0) continue;

		vec3 visibility = vec3(1.0);
#if defined RT_HANDHELD_SHADOWS || defined RT_GLASS_ENABLED
		if (!handMask && dist > 0.15) {
			int sampleCount = RT_HANDHELD_RADIUS > 0.0 ? RT_HANDHELD_SOFT_SAMPLES : 1;
			mat3 lightBasis = BuildOrthonormalBasis(lightDir);
			vec3 origin = viewPos + viewGeoNormal * max(0.008, abs(viewPos.z) * 8e-5);
			visibility = vec3(0.0);
			for (int sampleIndex = 0; sampleIndex < sampleCount; ++sampleIndex) {
				// Stable disk samples replace per-pixel/per-frame random binary shadows.
				vec2 disk = sampleVogelDisk(uint(sampleIndex), uint(sampleCount), dither * 6.2831853);
				vec3 shadowTarget = lightPos + lightBasis * vec3(disk * RT_HANDHELD_RADIUS, 0.0);
				vec3 sampleVisibility = vec3(1.0);
#if defined RT_HANDHELD_SHADOWS || defined RT_GLASS_ENABLED
				vec3 playerOrigin = transMAD(gbufferModelViewInverse, origin);
                vec3 playerTarget = transMAD(gbufferModelViewInverse, shadowTarget);
#ifdef RT_HANDHELD_SHADOWS
                sampleVisibility = RTTraceLocalVisibility(playerOrigin,playerTarget);
#else
                sampleVisibility = RTTraceLocalVisibility(playerOrigin,playerTarget,false);
#endif
#endif
				visibility += sampleVisibility / float(sampleCount);
			}
		}
#endif
		float flicker = 1.0;
#ifdef RT_HANDHELD_FLICKER
		if (itemID == 10001 || itemID == 10002) {
			float t = frameTimeCounter + float(hand) * 7.0;
			flicker += 0.035 * sin(t * 13.0) + 0.02 * sin(t * 29.0);
		}
#endif
		float attenuation = sqr(saturate(1.0 - pow4(dist / range))) / max(dist2 + sqr(RT_HANDHELD_RADIUS), 0.25);
		// Level-normalised so a level 15 item peaks near a placed blocklight source
		// instead of eight times brighter than one.
		float levelScale = sqr(clamp(float(level) * rcp(15.0), 0.0, 1.0));
		vec3 incident = RTHeldColor(itemID) * (levelScale * 1.25 * HELD_LIGHT_BRIGHTNESS * BLOCKLIGHT_BRIGHTNESS
			* attenuation * flicker * visibility);
		diffuse += incident * NdotL;
		vec3 halfVector = lightDir + viewDir;
		if (material.specularMask && dot(halfVector, halfVector) > EPS) {
			halfVector = normalize(halfVector);
			specular += incident * NdotL * SpecularGGX(saturate(dot(viewDir, halfVector)),
				max(dot(viewNormal, viewDir), 1e-4), NdotL, saturate(dot(viewNormal, halfVector)),
				max(material.roughness, 0.02), material.reflectance);
		}
	}
}

#endif
