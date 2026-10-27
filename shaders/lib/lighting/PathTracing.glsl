// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
// Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
/* Revelation RT modifications, 2026-10-26. Apache-2.0.
 * Screen-space diffuse paths with an independent direct-radiance cache.
 * This is software ray tracing; geometry outside the depth buffer is unavailable.
 */
#ifndef INCLUDE_LIB_LIGHTING_PATH_TRACING
#define INCLUDE_LIB_LIGHTING_PATH_TRACING

#include "/lib/lighting/SSRT.glsl"
#include "/lib/universal/MonteCarlo.glsl"
#include "/lib/surface/Material.glsl"
#include "/lib/lighting/Common.glsl"
#ifdef RT_GLASS_ENABLED
#include "/lib/lighting/GlassGrid.glsl"
#endif

#ifdef RT_LOCAL_LIGHTS
#include "/lib/lighting/LightTiles.glsl"
#endif

vec3 RTLimitRadiance(vec3 radiance) {
	if (any(isnan(radiance))) return vec3(0.0);
	radiance = clamp(radiance, vec3(0.0), vec3(FP16_MAX));
	return radiance * min(1.0, RT_RADIANCE_CLAMP / max(luminance(radiance), EPS));
}

vec3 RTEnvironment(vec3 direction, float skylight) {
	vec3 radiance = vec3(0.0);
#if defined DIMENSION_OVERWORLD
	if (isEyeInWater == 0) {
		radiance = textureLod(skyEnvMapTex, saturate(ProjectSkyMap(direction)), 0.0).rgb * cube(skylight);
	}
	radiance += max(MINIMUM_AMBIENT_BRIGHTNESS, 5e-3 * nightVision);
#elif defined DIMENSION_NETHER
	radiance = (netherColorCustom + 0.5) * (1.0 + nightVision);
#endif
	return RTLimitRadiance(radiance);
}

vec4 CalculatePathTracedDiffuse(ivec2 texel, vec3 viewPos, vec3 worldNormal, float skylight) {
	vec3 radiance = vec3(0.0);
	float visibility = 0.0;
	uint rng = initRandomState(uvec2(texel), uint(frameCounter));
	vec2 blueNoise = SampleStbnVec2(texel, frameCounter);

	for (int sampleIndex = 0; sampleIndex < RTGI_SAMPLES; ++sampleIndex) {
		vec3 throughput = vec3(1.0);
		vec3 pathPos = viewPos;
		vec3 pathNormal = worldNormal;
		float pathSkylight = skylight;

		for (int bounce = 0; bounce < RTGI_BOUNCES; ++bounce) {
			vec2 noise = fract(blueNoise + R2(sampleIndex + bounce * RTGI_SAMPLES) + nextVec2(rng));
			vec3 worldRay = BuildOrthonormalBasis(pathNormal) * SampleCosineHemisphereConcentric(noise);
			vec3 viewRay = mat3(gbufferModelView) * worldRay;
			float bias = max(0.02, abs(pathPos.z) * 2e-4);
			vec3 origin = pathPos + mat3(gbufferModelView) * pathNormal * bias;
			vec3 hit;
			if (!TraceScreenRay(origin, viewRay, nextFloat(rng), uint(SSRT_MAX_SAMPLES), RT_MAX_DISTANCE, hit)) {
				#ifdef RT_GLASS_ENABLED
                throughput *= RTTraceGlass(origin, origin + viewRay * RT_MAX_DISTANCE);
#endif
                radiance += throughput * RTEnvironment(worldRay, pathSkylight);
				if (bounce == 0) visibility += 1.0;
				break;
			}

			#ifdef RT_GLASS_ENABLED
            throughput *= RTTraceGlass(origin, ScreenToViewPos(hit));
#endif
            ivec2 hitTexel = clamp(uvToTexelScaled(hit.xy), ivec2(0), ivec2(scaledViewSize) - 1);
			vec3 hitNormal = FetchSurfaceNormal(hitTexel);
			// Reject the back of a single-layer depth surface rather than leaking its radiance.
			if (dot(hitNormal, -worldRay) <= 0.0) break;
			vec3 albedo = FetchBaseColor(hitTexel);
			uvec4 pack = loadMaterialPack(hitTexel);
			Material material = GetMaterialData(ExtractSpecularTex(pack), albedo);
			vec2 lightmap = Unpack2x8U(pack.x);
			vec3 hitWorld = transMAD(gbufferModelViewInverse, ScreenToViewPos(hit));

			// A disoccluded surface has no valid cache yet. Emission and the vanilla
			// block-light field provide a conservative first-frame fallback.
			vec3 emission = vec3(0.0);
#if EMISSIVE_MODE > 0 && defined MC_SPECULAR_MAP
			emission += material.emissive * albedo;
#endif
#if EMISSIVE_MODE < 2
			emission += HardCodeEmissive(pack.y, albedo, hitWorld) * EMISSIVE_BRIGHTNESS * albedo;
#endif
            if (pack.y != 500u && pack.y != 2000u) emission = RTAdjustBlockEmission(emission);
			float fallbackBlocklight = CalculateBlocklightFalloff(lightmap.x);
            vec3 fallback = emission + albedo * blocklightColor * fallbackBlocklight;
			vec4 direct = texelFetch(colortex10, hitTexel, 0);
			float edge = smoothstep(0.0, 0.04, minOf(min(hit.xy, 1.0 - hit.xy)));
			radiance += throughput * RTLimitRadiance(mix(fallback, direct.rgb, direct.a * edge));

			// Direct light is added exactly once per vertex. The cache excludes GI,
			// so increasing the bounce count does not recursively count old GI again.
			throughput *= clamp(albedo * (1.0 - material.metallic), vec3(0.0), vec3(0.98));
			if (maxOf(throughput) < 0.01) break;
			pathPos = ScreenToViewPos(hit);
			pathNormal = hitNormal;
			pathSkylight = lightmap.y;
		}
	}
	return vec4(RTLimitRadiance(radiance / float(RTGI_SAMPLES)), visibility / float(RTGI_SAMPLES));
}

#endif
