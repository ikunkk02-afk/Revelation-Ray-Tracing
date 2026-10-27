// Revelation RT v8, 2026-10-27. Apache-2.0.
#ifndef RT_LIGHT_TILES
#define RT_LIGHT_TILES
#include "/lib/lighting/SceneGrid.glsl"
uniform usampler2D rtLightTilesTex;
uniform usampler2D rtLightTilesHiTex;
uvec4 RTLightMask(ivec2 pixel, int halfIndex) {
    ivec2 tile = clamp(pixel / 16, ivec2(0), textureSize(rtLightTilesTex, 0) - 1);
    if (halfIndex == 0) return texelFetch(rtLightTilesTex, tile, 0);
    if (rtScene.lightCount <= 128u) return uvec4(0u);
    return texelFetch(rtLightTilesHiTex, tile, 0);
}
bool RTLocalCovered(ivec2 pixel) {
    return any(notEqual(RTLightMask(pixel, 0), uvec4(0u))) || any(notEqual(RTLightMask(pixel, 1), uvec4(0u)));
}
#endif
