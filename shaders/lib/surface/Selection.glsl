// Revelation RT v7, Apache-2.0. Selection is a display overlay, never a light.
#ifndef RT_SELECTION_OVERLAY
#define RT_SELECTION_OVERLAY
#define SELECTION_BOX_COLOR_R 0.05 // [0.0 0.05 0.1 0.15 0.2 0.25 0.3 0.35 0.4 0.45 0.5 0.55 0.6 0.65 0.7 0.75 0.8 0.85 0.9 0.95 1.0]
#define SELECTION_BOX_COLOR_G 0.05 // [0.0 0.05 0.1 0.15 0.2 0.25 0.3 0.35 0.4 0.45 0.5 0.55 0.6 0.65 0.7 0.75 0.8 0.85 0.9 0.95 1.0]
#define SELECTION_BOX_COLOR_B 0.05 // [0.0 0.05 0.1 0.15 0.2 0.25 0.3 0.35 0.4 0.45 0.5 0.55 0.6 0.65 0.7 0.75 0.8 0.85 0.9 0.95 1.0]
const uint rtSelectionMaterial = 501u;
vec3 RTSelectionDisplayColor() {
    return vec3(SELECTION_BOX_COLOR_R, SELECTION_BOX_COLOR_G, SELECTION_BOX_COLOR_B);
}
#endif
