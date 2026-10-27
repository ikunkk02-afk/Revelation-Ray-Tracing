// Modified for the Revelation Ray Tracing fork, 2026-10-27. See MODIFICATIONS.md; original license notices retained.
/*
--------------------------------------------------------------------------------

	Revelation Shaders

	Copyright (C) 2026 HaringPro
	Apache License 2.0

--------------------------------------------------------------------------------
*/

//======// Utility //=============================================================================//

#include "/lib/Utility.glsl"
#include "/lib/surface/Selection.glsl"


//======// Output //==============================================================================//

flat out vec4 vertColor;
flat out uint selectionOverlay;
out vec2 lightmap;

//======// Uniform //=============================================================================//

uniform int renderStage;
uniform vec2 taaJitter;
uniform vec2 renderScale;

//======// Main //================================================================================//
void main() {
	vertColor = gl_Color;
	selectionOverlay = uint(renderStage == MC_RENDER_STAGE_OUTLINE);
	lightmap = saturate((gl_MultiTexCoord1.xy - 8.0) * rcp(232.0));

	if (renderStage == MC_RENDER_STAGE_OUTLINE) {
		vertColor.rgb = vec3(SELECTION_BOX_COLOR_R, SELECTION_BOX_COLOR_G, SELECTION_BOX_COLOR_B);
		lightmap = vec2(0.0);
	}

	vec3 viewPos = transMAD(gl_ModelViewMatrix, gl_Vertex.xyz);
    gl_Position = project(gl_ProjectionMatrix, viewPos);
    #ifdef SHOULD_APPLY_JITTER
        if (selectionOverlay == 0u) gl_Position.xy += taaJitter * gl_Position.w;
    #endif
    #if (RENDER_SCALE_1000X != 1000) || SR_ENABLE
        gl_Position.xy = gl_Position.xy * renderScale + (renderScale - 1.0) * gl_Position.w;
    #endif
}
