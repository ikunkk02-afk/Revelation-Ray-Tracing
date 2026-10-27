// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
/* Revelation RT modifications, 2026-10-26. Apache-2.0.
 * v2: deterministic contact shadows and nearby stained-glass transmission.
 * v7.1: collision-constrained hand proxies resolved once per frame.
 * Proxies approximate the hands; animated item meshes are not tracked.
 */
#ifndef INCLUDE_LIB_LIGHTING_HANDHELD_TRACING
#define INCLUDE_LIB_LIGHTING_HANDHELD_TRACING
#include "/lib/lighting/LightSourceControls.glsl"
#ifdef COLORED_HANDHELD_LIGHTING
#include "/lib/lighting/HandheldAlbedo.glsl"
#endif

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
#include "/lib/lighting/HandheldPosition.glsl"

vec3 RTHeldColor(int itemID) {
#ifdef HELD_LIGHT_CUSTOM_COLOR
    return vec3(HELD_LIGHT_COLOR_R, HELD_LIGHT_COLOR_G, HELD_LIGHT_COLOR_B) * sRGB_2_Rec2020;
#else
	// Known emitters retain their intended color even when the item is hidden.
	if (itemID == 10001 || itemID == 10005) return vec3(1.0, 0.60, 0.22) * sRGB_2_Rec2020;
	if (itemID == 10002 || itemID == 10006) return vec3(0.12, 0.75, 1.0) * sRGB_2_Rec2020;
	if (itemID == 10003 || itemID == 10007) return vec3(1.0, 0.03, 0.01) * sRGB_2_Rec2020;
	if (itemID == 10004) return vec3(0.75, 0.95, 1.0) * sRGB_2_Rec2020;
#ifdef COLORED_HANDHELD_LIGHTING
	return mix(vec3(1.0, 0.65, 0.25) * sRGB_2_Rec2020, handheldAlbedo.average.rgb, handheldAlbedo.average.a);
#else
	return vec3(1.0, 0.65, 0.25) * sRGB_2_Rec2020;
#endif
#endif
}

void AddTracedHandheldLighting(vec3 viewPos, vec3 worldNormal, vec3 geometryNormal, Material material,
	bool handMask, float dither, ivec2 texel, inout vec3 diffuse, inout vec3 specular) {
    if (HELD_LIGHT_BRIGHTNESS <= 0.0) return;
	vec3 viewNormal = mat3(gbufferModelView) * worldNormal;
	vec3 viewGeoNormal = mat3(gbufferModelView) * geometryNormal;
	vec3 viewDir = normalize(-viewPos);
	for (int hand = 0; hand < 2; ++hand) {
		int level = hand == 0 ? heldBlockLightValue : heldBlockLightValue2;
		if (level <= 0) continue;
		int itemID = hand == 0 ? heldItemId : heldItemId2;
		vec4 source = rtHandheld.source[hand];
		vec3 lightPos = source.xyz;
		float sourceRadius = source.w;
		vec3 toLight = lightPos - viewPos;
		float dist2 = dot(toLight, toLight);
		float dist = sqrt(max(dist2, 1e-6));
		float range = RTHandheldRange(itemID, level);
		if (dist >= range) continue;
        float beam = RTHandheldBeamFactor(itemID, viewPos);
        if (beam <= 0.0) continue;
		vec3 lightDir = toLight / dist;
		float NdotL = saturate(dot(viewNormal, lightDir));
		if (NdotL <= 0.0) continue;

		vec3 visibility = vec3(1.0);
#if defined RT_HANDHELD_SHADOWS || defined RT_GLASS_ENABLED
		if (!handMask && dist > 0.02) {
			int sampleCount = sourceRadius > 0.0 ? RT_HANDHELD_SOFT_SAMPLES : 1;
			mat3 lightBasis = BuildOrthonormalBasis(lightDir);
			vec3 origin = viewPos + viewGeoNormal * max(0.008, abs(viewPos.z) * 8e-5);
			visibility = vec3(0.0);
			for (int sampleIndex = 0; sampleIndex < sampleCount; ++sampleIndex) {
				// Source-fixed quadrature. BlueNoise changes every pixel and frame;
				// rotating a two-tap shadow by it produces visible salt-and-pepper noise.
				vec2 disk = sampleCount > 1 ? sampleVogelDisk(uint(sampleIndex), uint(sampleCount), float(hand) * 2.39996323) : vec2(0.0);
				vec3 shadowTarget = lightPos + lightBasis * vec3(disk * sourceRadius, 0.0);
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
		if (itemID == 10001 || itemID == 10002 || itemID == 10005 || itemID == 10006) {
			float t = frameTimeCounter + float(hand) * 7.0;
			flicker += 0.035 * sin(t * 13.0) + 0.02 * sin(t * 29.0);
		}
#endif
		float attenuation = sqr(saturate(1.0 - pow4(dist / range))) / max(dist2 + sqr(sourceRadius), 0.25);
		// Level-normalised so a level 15 item peaks near a placed blocklight source
		// instead of eight times brighter than one.
		float levelScale = sqr(clamp(float(level) * rcp(15.0), 0.0, 1.0));
		vec3 incident = RTHeldColor(itemID) * (levelScale * 1.25 * HELD_LIGHT_BRIGHTNESS
			* attenuation * flicker * beam * visibility);
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
