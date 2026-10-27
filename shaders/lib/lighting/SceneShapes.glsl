// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
// Generated vanilla model bounds, in sixteenths of a block.
#ifndef RT_SCENE_SHAPES
#define RT_SCENE_SHAPES
#include "/lib/lighting/SceneID.glsl"
uvec2 RTSceneInfo(uint i) { return texelFetch(rtSceneShapesTex, ivec2(int(i), 0), 0).xy; }
uvec2 RTShapeRange(uint i) { return texelFetch(rtSceneShapesTex, ivec2(int(i) + 556, 0), 0).xy; }
uint RTShapeBox(uint i) { return texelFetch(rtSceneShapesTex, ivec2(int(i) + 927, 0), 0).r; }
#endif
