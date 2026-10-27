// Revelation RT v9.3, Apache-2.0. Independent controls; no new trace samples.
#ifndef RT_LIGHT_SOURCE_CONTROLS
#define RT_LIGHT_SOURCE_CONTROLS

vec3 RTBlockLightChroma(vec3 nativeColor) {
#ifdef RT_BLOCK_CUSTOM_COLOR
    return vec3(BLOCKLIGHT_COLOR_R, BLOCKLIGHT_COLOR_G, BLOCKLIGHT_COLOR_B);
#else
    return nativeColor;
#endif
}

// Change source emission together with direct irradiance so GI does not keep
// bouncing white light from a source whose illumination was changed to red.
vec3 RTAdjustBlockEmission(vec3 emission) {
#ifdef RT_BLOCK_CUSTOM_COLOR
    vec3 color = vec3(BLOCKLIGHT_COLOR_R, BLOCKLIGHT_COLOR_G, BLOCKLIGHT_COLOR_B) * sRGB_2_Rec2020;
    return max(luminance(emission), 0.0) * color * BLOCKLIGHT_BRIGHTNESS;
#else
    return emission * BLOCKLIGHT_BRIGHTNESS;
#endif
}

bool RTTorchItem(int itemID) {
    return itemID == 10005 || itemID == 10006 || itemID == 10007;
}

bool RTUseFlashlight(int itemID) {
#ifdef RT_HANDHELD_FLASHLIGHT
    return RTTorchItem(itemID);
#else
    return false;
#endif
}

float RTHandheldRange(int itemID, int level) {
    return RTUseFlashlight(itemID) ? RT_FLASHLIGHT_RANGE : max(float(level), 2.0);
}

float RTHandheldBeamFactor(int itemID, vec3 viewPos) {
    if (!RTUseFlashlight(itemID)) return 1.0;
    if (viewPos.z >= -1e-5) return 0.0;
    // Camera-centred angular mask keeps the hotspot on the crosshair even near
    // a wall. Visibility still uses the collision-constrained hand source.
    float cosTheta = -viewPos.z * inversesqrt(max(dot(viewPos, viewPos), 1e-8));
    float halfAngle = RT_FLASHLIGHT_FOV * (PI / 360.0);
    float cosOuter = cos(halfAngle);
    if (cosTheta <= cosOuter) return 0.0;
    float radial = saturate((1.0 - cosTheta) / max(1.0 - cosOuter, 1e-5));
    float hotspot = 0.35 + 0.65 * sqr(1.0 - radial);
    if (RT_FLASHLIGHT_SOFTNESS <= 0.0) return hotspot;
    float cosInner = cos(halfAngle * (1.0 - RT_FLASHLIGHT_SOFTNESS));
    return hotspot * smoothstep(cosOuter, max(cosInner, cosOuter + 1e-5), cosTheta);
}

#endif
