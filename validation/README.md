# v9.3 offline validation evidence

The seven `*-v93.json` reports in this directory describe the exact shader tree identified by their shared `source_digest`. `scripts/build_release.py` rejects failed or stale reports before packaging. CI checks this evidence and package/source equality; it does not rerun GPU tests on the hosted runner.

These are offline checks, not a Minecraft frame-rate measurement, general hardware certification or complete optional-mod compatibility test.

## Rerunning locally

Use a GPU/driver with an OpenGL 4.6 compatibility context, Python and `scripts/requirements-rt-validation.txt`. Run from the repository root:

```sh
python scripts/validate_rt_v8.py --report-name compile-v93.json
python scripts/probe_rt_v8_regression.py --report-name physical-probes-v93.json
python scripts/light_controls_v93_checks.py
python scripts/shadow_projection_v92_checks.py --report-name shadow-projection-v93.json --preview-name shadow-projection-v93.png
python scripts/seam_checks.py --report-name seam-v93.json --preview-name seam-v93.png
python scripts/dense_lights_v8_checks.py --report-name dense-lights-v93.json --preview-name dense-lights-v93.png
```

The shadow-projection failing control requires the historical `Revelation-RT-v9.1-StableShadows.zip`; seam and dense-light controls require `Revelation-RT-v7.1-HandheldFix.zip`. Those development snapshots are expected in a `deliverables` directory two levels above the checkout, as specified in the scripts. They are not bundled with this release. Compile, physical-probe and light-control checks use the checked-in source/data without those archives.

The Iris metadata checker requires Java 21 (`java`, `javac`, `javap` on PATH), the target Iris JAR and Minecraft libraries:

```sh
python scripts/check_iris_metadata.py --iris /path/to/iris-fabric-1.8.14-beta.1+mc1.21.1.jar --libraries /path/to/minecraft/libraries --report-name iris-metadata-v93.json
```

It reads the supplied files without launching Minecraft or modifying the game instance. Other scripts retained for historical development may require old snapshots and are not the v9.3 release gate.
