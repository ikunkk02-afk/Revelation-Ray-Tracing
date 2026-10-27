# Fork modification record

Revelation Ray Tracing v9.3, 2026-10-27.

Upstream: [HaringPro/Revelation](https://github.com/HaringPro/Revelation), dev commit `d5911393856d9dd97375b46a1a088e6b8fddd755`. Fork: [ikunkk02-afk/Revelation-Ray-Tracing](https://github.com/ikunkk02-afk/Revelation-Ray-Tracing). This is a modified distribution, not an official upstream release.

The original Apache-2.0 license, HaringPro copyright and upstream contributor/third-party notices are retained. RT additions and modifications are distributed under Apache-2.0, except where existing third-party terms apply.

## Changes

- Local multi-light visibility and software ray tracing, cutout apertures, colored-glass transmission and handheld source collision constraints.
- Stable single-center local/handheld shadow projections by default, instead of noisy or overlapping area-light samples.
- Edge-aware half-resolution local lighting, material interpretation fixes and six quality profiles.
- Independent block/held brightness and RGB controls; optional view-directed flashlight for regular, soul and redstone torches.
- Bilingual settings, offline validation scripts/reports, documentation and release packaging.

## Modified upstream shader files

- `shaders/block.properties`
- `shaders/lang/en_US.lang`
- `shaders/lang/zh_CN.lang`
- `shaders/lib/atmosphere/AtmosphericFog.glsl`
- `shaders/lib/atmosphere/clouds/Common.glsl`
- `shaders/lib/Config.glsl`
- `shaders/lib/lighting/Common.glsl`
- `shaders/lib/lighting/shadow/Render.glsl`
- `shaders/lib/lighting/SSILVB.glsl`
- `shaders/lib/lighting/SSR.glsl`
- `shaders/lib/lighting/SSRT.glsl`
- `shaders/lib/Setting.glsl`
- `shaders/lib/surface/Material.glsl`
- `shaders/lib/universal/Uniform.glsl`
- `shaders/lib/Utility.glsl`
- `shaders/program/CombineLighting.frag`
- `shaders/program/diffuse/Accumulate.frag`
- `shaders/program/diffuse/DiffuseIndirect.comp`
- `shaders/program/diffuse/VarianceEstimate.comp`
- `shaders/program/gbuffers/Basic.frag`
- `shaders/program/gbuffers/Basic.vert`
- `shaders/program/gbuffers/Block.vert`
- `shaders/program/gbuffers/Terrain.vert`
- `shaders/program/gbuffers/Water.frag`
- `shaders/program/gbuffers/Water.vert`
- `shaders/program/IntegrateScene.frag`
- `shaders/program/post/Final.frag`
- `shaders/program/post/Grade.frag`
- `shaders/program/ReprojectScene.comp`
- `shaders/program/shadow/Shadow.frag`
- `shaders/program/shadow/Shadow.vert`
- `shaders/program/specular/SpecularIndirect.frag`
- `shaders/program/Translucent.comp`
- `shaders/program/VolumetricFog.frag`
- `shaders/shaders.properties`
- `shaders/world0/begin.csh`

## Added shader files

- `shaders/item.properties`
- `shaders/lib/lighting/Emitters.glsl`
- `shaders/lib/lighting/GlassGrid.glsl`
- `shaders/lib/lighting/GlassMaterial.glsl`
- `shaders/lib/lighting/GlassOptics.glsl`
- `shaders/lib/lighting/HandheldPosition.glsl`
- `shaders/lib/lighting/HandheldTracing.glsl`
- `shaders/lib/lighting/LightSourceControls.glsl`
- `shaders/lib/lighting/LightTiles.glsl`
- `shaders/lib/lighting/LocalLightCache.glsl`
- `shaders/lib/lighting/LocalLights.glsl`
- `shaders/lib/lighting/LocalVisibility.glsl`
- `shaders/lib/lighting/LocalVolumetrics.glsl`
- `shaders/lib/lighting/LocalWeight.glsl`
- `shaders/lib/lighting/PathTracing.glsl`
- `shaders/lib/lighting/SceneGrid.glsl`
- `shaders/lib/lighting/SceneID.glsl`
- `shaders/lib/lighting/SceneShapes.glsl`
- `shaders/lib/surface/Selection.glsl`
- `shaders/program/prepare/BuildLocalHierarchy.comp`
- `shaders/program/prepare/ClearGlassGrid.comp`
- `shaders/program/prepare/ClearSceneGrid.comp`
- `shaders/program/prepare/ResolveHandheldPosition.comp`
- `shaders/program/prepare/SelectLocalLights.comp`
- `shaders/program/prepare/TraceLocalDiffuse.comp`
- `shaders/texture/rt/scene_alpha.bin`
- `shaders/texture/rt/scene_shapes.bin`
- `shaders/world-1/begin.csh`
- `shaders/world-1/begin1.csh`
- `shaders/world-1/begin2.csh`
- `shaders/world-1/deferred.csh`
- `shaders/world-1/deferred18.csh`
- `shaders/world-1/deferred20.csh`
- `shaders/world-1/shadowcomp.csh`
- `shaders/world0/begin1.csh`
- `shaders/world0/begin2.csh`
- `shaders/world0/deferred.csh`
- `shaders/world0/deferred18.csh`
- `shaders/world0/deferred20.csh`
- `shaders/world0/shadowcomp.csh`

README files are rewritten for the fork; .gitignore is extended for build outputs and .gitattributes normalizes source checkouts while preserving language-file bytes for reproducible source digests. All other new documentation, validation, CI and packaging files are fork additions.
