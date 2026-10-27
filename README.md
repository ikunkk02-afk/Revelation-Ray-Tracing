<!-- Modified for the Revelation Ray Tracing fork, 2026-10-27. Apache-2.0. -->
# Revelation Ray Tracing

[简体中文](README.zh-CN.md) | **English**

A modified Minecraft shaderpack based on [HaringPro/Revelation](https://github.com/HaringPro/Revelation). This fork adds local multi-light software ray tracing, colored-glass transmission and configurable held lighting. It is maintained separately from upstream.

## Download and install

**Current version: v9.3 — Light Controls.** Download `Revelation-RT-v9.3-LightControls.zip` from [Releases](https://github.com/ikunkk02-afk/Revelation-Ray-Tracing/releases/latest). Put the ZIP, without extracting it, into your Minecraft instance's `shaderpacks` folder and select it in Iris. GitHub's automatic source-code archives are for developers.

Target: Minecraft **1.21.1 Fabric**, Iris **1.8.14-beta.1**, OpenGL **4.6**. Offline GPU validation used an RTX 5060 Laptop GPU. Other hardware, Iris versions and optional integrations need testing. OptiFine is not supported.

Start with **High** or **Ultra**, then adjust to your frame rate; **Ray Tracing** is the most demanding preset. The shipped default is Ultra. Software ray tracing does not require or invoke hardware RTX ray-tracing cores.

## Features and controls

- Stable single-center shadows for placed and held emitters by default; cutout apertures and colored-glass transmission.
- Multi-light illumination, edge-aware half-resolution local lighting and corrected material interpretation.
- Six presets: Original default, Low, Medium, High, Ultra and Ray Tracing.
- **Light sources / flashlight** in Shader Pack Settings: independent block and held brightness, optional RGB overrides, and a flashlight mode for regular, soul and redstone torches in either hand.
- Flashlight beam width, soft edge and range controls. It illuminates surfaces; it does not add a visible volumetric beam in air. Other held lights keep omnidirectional illumination.

Custom colors and flashlight mode are off by default. These personal settings survive quality-preset changes. For a white flashlight, enable flashlight and held custom color, set RGB to 1/1/1 and start at held brightness 1.

[Detailed v9.3 settings (Chinese)](docs/RT_V9_3_LIGHT_CONTROLS.zh-CN.md) · [Stable-shadow design](docs/RT_V9_2_PROJECTION.zh-CN.md) · [Modification record](MODIFICATIONS.md)

## Validation and limits

The release includes offline results for 656 shader compile/link checks, 414 behavior checks (622,592 rays), 21 light-control checks, 10 single-projection checks, plus seam, dense-light and installed-Iris metadata checks. These checks do not measure Minecraft frame rate or guarantee visual quality on every scene. In-game testing is performed by the user.

Local lighting uses a finite scene grid and indirect light uses screen-space information. The default shadow is a point-source approximation; experimental area-light options may show multiple projections. Existing Voxy, Distant Horizons, Physics Mod, Super Resolution and HDR integration code is retained from upstream; these combinations were not validated for this RT release.

## Build

Python 3.10+ is sufficient to reproduce the shader ZIP from the tagged sources and verify the bundled reports:

```sh
python scripts/build_release.py --output-dir dist
```

This packages GLSL source and bundled assets; Iris compiles the shaders at runtime. [GPU validation instructions and historical-control prerequisites](validation/README.md) explain how to rerun the checks; these require a compatible OpenGL context, and some comparison tests need earlier development archives. Iris metadata checks also require Java 21 and the target Iris/dependency JARs. [Release notes](docs/RELEASE_v9.3.md).

## Credits

- [HaringPro](https://github.com/HaringPro) — Revelation.
- [Yong-Xin Mo](https://github.com/moyongxin) — code contributions and technical guidance.
- [GeForceLegend](https://github.com/GeForceLegend) — code contributions and debugging.
- [FactoriZation](https://github.com/FactoriZation000) — development assistance and AMD GPU testing.
- [NASA Scientific Visualization Studio](https://svs.gsfc.nasa.gov) — star map and lunar imagery.

## License

The original **[Apache License 2.0](LICENSE)** is retained for Revelation and this fork's RT additions/modifications. Original authorship and separately licensed components remain identified in source. See [NOTICE](NOTICE), [third-party notices](THIRD_PARTY_NOTICES.md) and [MODIFICATIONS.md](MODIFICATIONS.md). This is not an upstream-endorsed release.
