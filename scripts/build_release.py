"""Package the v9.3 runtime shader ZIP after checking matching offline evidence.

Revelation Ray Tracing fork additions, 2026-10-27. Apache-2.0.
No GPU, Minecraft launch, credentials or installation changes are needed here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from rt_source_digest import SHADERS, source_digest

ROOT = SHADERS.parent
REPORTS = (
    'compile-v93.json', 'physical-probes-v93.json', 'iris-metadata-v93.json',
    'light-controls-v93.json', 'shadow-projection-v93.json',
    'seam-v93.json', 'dense-lights-v93.json',
)


def check_reports(digest):
    reports = {}
    for name in REPORTS:
        report = json.loads((ROOT / 'validation' / name).read_text(encoding='utf-8'))
        if report.get('source_digest') != digest:
            raise ValueError(f'Stale validation report: {name}; rerun GPU/metadata validation')
        checks = report.get('checks') or report.get('tests')
        if report.get('passed') is False or (checks and not all(c['passed'] for c in checks)):
            raise ValueError(f'Failed validation report: {name}')
        if not report.get('passed') and not checks:
            raise ValueError(f'Missing pass evidence: {name}')
        reports[name] = report
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    config = json.loads((ROOT / 'release.json').read_text(encoding='utf-8'))
    if config['tag'] != 'v' + config['version'] or config['license'] != 'Apache-2.0':
        raise ValueError('Release tag/version/license mismatch')
    digest = source_digest()
    reports = check_reports(digest)
    files = [p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT / name for name in (
        'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md', 'MODIFICATIONS.md',
        'README.md', 'README.zh-CN.md', 'release.json',
    )]
    files += list((ROOT / 'docs').rglob('*.md'))
    files += [ROOT / 'validation' / name for name in (*REPORTS, 'README.md')]
    files = sorted(set(files), key=lambda p: p.relative_to(ROOT).as_posix())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    package = args.output_dir / (config['artifact'] + '.zip')
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), (2026, 10, 27, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes(), compresslevel=6)
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        for path in files:
            if archive.read(path.relative_to(ROOT).as_posix()) != path.read_bytes():
                raise ValueError(f'Package/source mismatch: {path}')
        for required in ('shaders/shaders.properties', 'LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md'):
            if required not in archive.namelist():
                raise ValueError(f'Missing runtime/license file: {required}')
    if digest != source_digest():
        raise ValueError('Sources changed while building')
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest = {
        **config, 'source_digest': digest, 'package': package.name, 'sha256': sha,
        'bytes': package.stat().st_size, 'files': len(files),
        'compile_checks': len(reports['compile-v93.json']['checks']),
        'behavior_checks': reports['physical-probes-v93.json']['behavior_checks'],
        'behavior_rays': reports['physical-probes-v93.json']['behavior_rays'],
        'light_controls_checks': len(reports['light-controls-v93.json']['tests']),
        'projection_checks': len(reports['shadow-projection-v93.json']['tests']),
        'validation_reports': {name: hashlib.sha256((ROOT / 'validation' / name).read_bytes()).hexdigest()
                               for name in REPORTS},
        'scope': 'Offline shader/GPU/Iris metadata validation; not Minecraft FPS or broad mod compatibility',
    }
    manifest_path = args.output_dir / 'RT-v9.3-build-manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    checksums = []
    for path in (package, manifest_path):
        checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
    (args.output_dir / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
