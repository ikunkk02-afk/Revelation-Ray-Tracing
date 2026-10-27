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

/* RENDERTARGETS: 6,7 */
layout(location = 0) out vec4 albedoOut;
layout(location = 1) out uvec4 materialOut;

//======// Input //===============================================================================//

flat in vec4 vertColor;
flat in uint selectionOverlay;
in vec2 lightmap;

//======// Uniform //=============================================================================//

uniform float alphaTestRef;

uniform vec2 scaledViewSize;

//======// Main //================================================================================//
void main() {
    #if (RENDER_SCALE_1000X != 1000) || SR_ENABLE
        if (any(greaterThanEqual(gl_FragCoord.xy, scaledViewSize))) {
            discard;
        }
    #endif

	if (vertColor.a < alphaTestRef) discard;

	albedoOut = vec4(vertColor.rgb, 1.0);

	materialOut = uvec4(Pack2x8U(lightmap), lightmap.x > 0.999 ? 20u : 1u, 0u, 0u);
    if (selectionOverlay != 0u) {
        albedoOut.rgb = vec3(0.0);
        materialOut = uvec4(0u, rtSelectionMaterial, 0u, 0u);
    }
}
