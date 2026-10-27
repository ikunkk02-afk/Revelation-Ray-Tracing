"""Package the seam/startup fix from a tree whose GPU reports are current.

Writes deliverables/Revelation-RT-v8.2-*.zip, the build manifest and the Iris
option file that keeps the first load inside a few seconds of shader linking.
"""
from pathlib import Path
import hashlib
import json
import zipfile

from rt_source_digest import SHADERS, source_digest

ROOT = SHADERS.parent
OUT = ROOT.parent.parent / 'deliverables'
NAME = 'Revelation-RT-v8.2-SeamStartupFix'

FIRST_LOAD_OPTIONS = """#Tue Oct 27 10:00:00 CST 2026
INFO=1
MOD_BLOCK_SUPPORT=true
PLANET_GROUND=true
RP_SUPPORT=true
shadowMapResolution=2048
shadowDistance=128.0
SSILVB_SLICE_COUNT=1
SSILVB_SAMPLE_COUNT=16
SSRT_MAX_SAMPLES=16
SSRT_REFINEMENT_STEPS=4
PCSS_SEARCH_SAMPLES=8
PCSS_FILTER_SAMPLES=16
CLOUD_LOW_SAMPLES_MIN=20
CLOUD_LOW_SAMPLES_MAX=40
CLOUD_LOW_SUNLIGHT_SAMPLES=6
VF_MAX_SAMPLES=16
UW_VF_MAX_SAMPLES=16
RTGI_SAMPLES=1
RTGI_BOUNCES=1
RT_MAX_DISTANCE=32.0
RT_SPECULAR_SAMPLES=1
RT_LOCAL_SHADOW_SAMPLES=4
RT_HANDHELD_SOFT_SAMPLES=4
RT_LOCAL_VOLUME_SAMPLES=4
RT_LOCAL_SOURCE_SIZE=0.65
RT_LOCAL_HALF_RES=true
"""


def main():
    digest = source_digest()
    seam = json.loads((ROOT / 'validation/seam-v8.json').read_text(encoding='utf-8'))
    dense = json.loads((ROOT / 'validation/dense-lights-v8.json').read_text(encoding='utf-8'))
    for report, name in ((seam, 'seam-v8.json'), (dense, 'dense-lights-v8.json')):
        assert report['source_digest'] == digest, ('Stale report', name)
        assert report['passed'], name
    link = json.loads((ROOT / 'validation/link-times-v8.2.json').read_text(encoding='utf-8'))

    files = [p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT / p for p in ('LICENSE', 'README.md', 'README.zh-CN.md',
                                 'docs/RT_V8_QUALITY.zh-CN.md', 'docs/RT_V8_2_SEAMS.zh-CN.md',
                                 'validation/seam-v8.json', 'validation/seam-v8.png',
                                 'validation/dense-lights-v8.json', 'validation/dense-lights-v8.png',
                                 'validation/link-times-v8.2.json')]
    files += [p for p in (ROOT / 'scripts').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [p for p in (ROOT / 'docs').rglob('*') if p.is_file()]
    files = sorted(set(files))

    manifest = {'version': 'Revelation RT v8.2 (tile seams + startup link time)',
                'date': '2026-10-27', 'target': 'Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1',
                'source_digest': digest, 'renderer': seam['renderer'],
                'seam': {'tests_passed': seam['passed'], 'scenes': seam['scenes']},
                'link_times': link, 'runtime_game_validation': False,
                'minecraft_fps_measured': False}
    (ROOT / 'validation/build-v8.2.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    files.append(ROOT / 'validation/build-v8.2.json')

    OUT.mkdir(exist_ok=True)
    package = OUT / f'{NAME}.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for p in files:
            assert z.read(p.relative_to(ROOT).as_posix()) == p.read_bytes(), p
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    (OUT / f'{NAME}.sha256').write_text(f'{sha}  {package.name}\n', encoding='utf-8')
    options = OUT / f'{NAME}.zip.txt'
    options.write_text(FIRST_LOAD_OPTIONS.replace('\n', '\r\n'), encoding='utf-8')
    print(json.dumps({'package': package.name, 'bytes': package.stat().st_size, 'files': len(files),
                      'sha256': sha, 'first_load_options': options.name}, indent=2))


if __name__ == '__main__':
    main()
