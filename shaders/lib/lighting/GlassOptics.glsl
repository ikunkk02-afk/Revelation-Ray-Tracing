// Revelation RT v5, Apache-2.0. Air -> glass -> air, in world metre units.
#ifndef RT_GLASS_OPTICS
#define RT_GLASS_OPTICS
#include "/lib/lighting/GlassMaterial.glsl"

// Returns the exiting ray, rather than extending the inside-glass ray through
// the whole background. Parallel window faces give a lateral displacement.
bool RTRefractGlass(vec3 viewPos, vec3 viewNormal, uint code,
    out vec3 exitViewPos, out vec3 exitViewDir, out float pathLength, out float exitTransmission) {
    vec3 incoming = normalize(viewPos);
    viewNormal = faceforward(normalize(viewNormal), incoming, normalize(viewNormal));
    vec3 inside = refract(incoming, viewNormal, 1.0 / max(GLASS_IOR, 1e-4));
    pathLength = 0.0; exitTransmission = 1.0;
    exitViewPos = viewPos; exitViewDir = incoming;
    if (dot(inside, inside) < 1e-8) { exitTransmission = 0.0; return false; }
    vec3 worldEntry = transMAD(gbufferModelViewInverse, viewPos);
    vec3 worldInside = mat3(gbufferModelViewInverse) * inside;
    vec3 probe = worldEntry + worldInside * 0.001;
    vec3 local = fract(probe + cameraPosition);
    vec3 exitNormal;
    vec2 segment = RTGlassFirstSegment(code, local, worldInside, exitNormal);
    if (segment.y <= segment.x || segment.x > 0.003) return true;
    pathLength = segment.y + 0.001;
    vec3 outgoing = refract(worldInside, -exitNormal, max(GLASS_IOR, 1e-4));
    exitTransmission = 1.0 - RTDielectricFresnel(dot(worldInside, exitNormal), 1.0 / max(GLASS_IOR, 1e-4));
    if (dot(outgoing, outgoing) < 1e-8) { exitTransmission = 0.0; return false; }
    exitViewPos = transMAD(gbufferModelView, worldEntry + worldInside * pathLength + outgoing * 0.002);
    exitViewDir = normalize(mat3(gbufferModelView) * outgoing);
    return true;
}
#endif
