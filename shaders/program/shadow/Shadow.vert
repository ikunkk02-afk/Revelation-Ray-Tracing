// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
// Revelation RT v2 modifications, 2026-10-26. Apache-2.0.
/*
--------------------------------------------------------------------------------

	Revelation Shaders

	Copyright (C) 2026 HaringPro
	Apache License 2.0

--------------------------------------------------------------------------------
*/

//======// Utility //=============================================================================//

#include "/lib/Utility.glsl"

//======// Output //==============================================================================//

out vec2 texCoord;
out vec3 vectorData; // Minecraft position in water, vertColor in other materials

flat out uint isWater;
flat out uint glassCode;
out vec3 rtGlassLocalPos;

//======// Attribute //===========================================================================//

in vec4 mc_Entity;
in vec4 at_tangent;
#if defined RT_GLASS_ENABLED || defined RT_SCENE_ENABLED
in vec4 at_midBlock;
#endif

//======// Uniform //=============================================================================//

uniform vec3 cameraPosition;
uniform mat4 shadowModelViewInverse;

uniform int blockEntityId;

//======// Function //============================================================================//

#include "/lib/lighting/shadow/Common.glsl"
#ifdef RT_GLASS_ENABLED
#define RT_GLASS_WRITE
#include "/lib/lighting/GlassGrid.glsl"
#endif

#ifdef RT_SCENE_ENABLED
#define RT_SCENE_WRITE
#include "/lib/lighting/SceneGrid.glsl"
#endif

//======// Main //================================================================================//
void main() {
    glassCode = 0u;
    rtGlassLocalPos = vec3(0.5);
#ifdef RT_GLASS_ENABLED
    rtGlassLocalPos = vec3(0.5) - at_midBlock.xyz / 64.0;
    glassCode = RTGlassCode(int(mc_Entity.x));
    if (glassCode != 0u) {
        vec3 shadowView = transMAD(gl_ModelViewMatrix, gl_Vertex.xyz);
        vec3 relativeCenter = transMAD(shadowModelViewInverse, shadowView) + at_midBlock.xyz / 64.0;
        RTRecordGlass(int(mc_Entity.x), relativeCenter);
    }
#endif
#ifdef RT_SCENE_ENABLED
    vec3 sceneCenter = transMAD(shadowModelViewInverse, transMAD(gl_ModelViewMatrix, gl_Vertex.xyz)) + at_midBlock.xyz / 64.0;
    RTRecordScene(int(mc_Entity.x), sceneCenter);
#endif
	if (blockEntityId == 10030) {
		gl_Position = vec4(-1.0);
		return;
	}

	#ifdef SHADOW_BACKFACE_CULLING
		if ((gl_NormalMatrix * gl_Normal).z < 0.0) {
			gl_Position = vec4(-1.0);
			return;
		}
	#endif

	texCoord = vec2(gl_TextureMatrix[0] * gl_MultiTexCoord0);

	vec3 viewPos = transMAD(gl_ModelViewMatrix, gl_Vertex.xyz);

	isWater = 0u;
	if (int(mc_Entity.x) == 10003) {
		isWater = 1u;
		vectorData = transMAD(shadowModelViewInverse, viewPos) + cameraPosition;
	} else {
		vectorData = gl_Color.rgb;
	}

	gl_Position.xyz = DistortShadowSpace(projMAD(gl_ProjectionMatrix, viewPos));
	gl_Position.w = 1.0;
}
