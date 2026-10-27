// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.
#ifndef RT_SCENE_ID
#define RT_SCENE_ID
uniform usampler2D rtSceneShapesTex;
const uint rtSceneClassCount = 556u;
uint RTSceneClass(int id) { return id > 20000 && id < 20000 + int(rtSceneClassCount) ? uint(id - 20000) : 0u; }
int RTBaseBlockID(int id) { uint i = RTSceneClass(id); return i > 0u ? 10000 + int(texelFetch(rtSceneShapesTex, ivec2(int(i), 0), 0).z) : id; }
#endif
