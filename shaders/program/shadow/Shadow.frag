// Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
/*
--------------------------------------------------------------------------------

	Revelation Shaders

	Copyright (C) 2026 HaringPro
	Apache License 2.0

--------------------------------------------------------------------------------
*/

#define PASS_SHADOW

//======// Utility //=============================================================================//

#include "/lib/Utility.glsl"

//======// Output //==============================================================================//

layout(location = 0) out vec3 shadowcolor0Out;
layout(location = 1) out vec4 shadowcolor1Out;

//======// Input //===============================================================================//

in vec2 texCoord;
in vec3 vectorData; // Minecraft position in water, vertColor in other materials

flat in uint isWater;
flat in uint glassCode;
in vec3 rtGlassLocalPos;

//======// Uniform //=============================================================================//

uniform sampler2D tex;

#include "/lib/universal/Uniform.glsl"

//======// Function //============================================================================//

#include "/lib/universal/Random.glsl"

#include "/lib/water/WaterWave.glsl"
#include "/lib/lighting/GlassMaterial.glsl"

//======// Main //================================================================================//
void main() {
    shadowcolor0Out = vec3(1.0);
    shadowcolor1Out = vec4(0.0);
	if (isWater == 1u) {
		vec3 waveNormal = CalculateWaterNormal(vectorData.xz);
		shadowcolor1Out = vec4(waveNormal.xzy * 0.5 + 0.5, 1.0);
	} else {
		vec4 albedo = texture(tex, texCoord);
		// Texture alpha-zero means clear bulk glass here, but an actual hole in
        // foliage, doors and grates. Preserve the glass interface for sunlight.
		if (glassCode == 0u && albedo.a < max(0.01, alphaTestRef)) discard;

		#ifdef RT_GLASS_ENABLED
        if (glassCode != 0u) {
            // The PCSS color buffer is decoded with a cube in shadow/Render.glsl.
            vec3 direction = normalize(shadowDirWorld);
            float thickness = RTGlassPathLength(glassCode, rtGlassLocalPos - direction * 2.0, direction, 4.0);
            vec3 transmission = RTGlassAbsorption(glassCode, thickness);
            shadowcolor0Out = pow(transmission, vec3(1.0 / 3.0));
        } else
#endif
        if (albedo.a < 254.5 / 255.0) {
            albedo.rgb *= 1.0 - 0.125 * albedo.a;
			shadowcolor0Out = pow(albedo.rgb * vectorData, vec3(approxSqrt(albedo.a + 0.25)));
		}

		shadowcolor1Out.w = glassCode != 0u ? 0.25 : 0.0;
	}
}
