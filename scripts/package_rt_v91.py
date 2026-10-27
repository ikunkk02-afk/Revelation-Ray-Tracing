"""Build v9.1 only from current successful validation reports."""
from pathlib import Path
import hashlib,json,zipfile
from rt_source_digest import SHADERS,source_digest

ROOT=SHADERS.parent;OUT=ROOT.parent.parent/'deliverables';NAME='Revelation-RT-v9.1-StableShadows'

def main():
    digest=source_digest();reports={}
    for name in ('compile-v91.json','physical-probes-v91.json','iris-metadata-v91.json',
                 'shadow-noise-v91.json','seam-v91.json','dense-lights-v91.json'):
        r=json.loads((ROOT/'validation'/name).read_text(encoding='utf-8'))
        assert r['source_digest']==digest,('Stale report',name)
        assert r.get('passed',bool(r.get('checks')) and all(c['passed'] for c in r.get('checks',[]))),name
        reports[name]=r
    with zipfile.ZipFile(OUT/'Revelation-RT-v9-Lighting.zip') as old:
        changed=[p.relative_to(ROOT).as_posix() for p in sorted(SHADERS.rglob('*')) if p.is_file() and
                 (p.relative_to(ROOT).as_posix() not in old.namelist() or old.read(p.relative_to(ROOT).as_posix())!=p.read_bytes())]
    summary=dict(version='Revelation RT v9.1 Stable Shadows',date='2026-10-27',source_digest=digest,
                 baseline='Revelation-RT-v9-Lighting.zip',changed_shader_files=changed,default_profile='Ultra',
                 compile_checks=len(reports['compile-v91.json']['checks']),
                 behavior_checks=reports['physical-probes-v91.json']['behavior_checks'],
                 behavior_rays=reports['physical-probes-v91.json']['behavior_rays'],
                 noise_checks=reports['shadow-noise-v91.json']['tests'],
                 minecraft_launched=False,minecraft_fps_measured=False,
                 performance_note='Four fixed shadow rays replace one stochastic ray per lamp/sample receiver; half-resolution cache retained. No guaranteed FPS.')
    build=ROOT/'validation/build-v91.json';build.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=[p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT/p for p in ('LICENSE','README.md','README.zh-CN.md','docs/RT_V9_LIGHTING.zh-CN.md','docs/RT_V9_1_SHADOWS.zh-CN.md')]
    files += [ROOT/'validation'/name for name in reports]
    files += [build,ROOT/'validation/shadow-noise-v91.png',ROOT/'validation/seam-v91.png',ROOT/'validation/dense-lights-v91.png']
    files += [p for p in (ROOT/'scripts').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files=sorted(set(files));package=OUT/(NAME+'.zip')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes(),str(p)
    sha=hashlib.sha256(package.read_bytes()).hexdigest()
    (OUT/(NAME+'.sha256')).write_text(sha+'  '+package.name+'\n',encoding='utf-8')
    manifest={**summary,'package':str(package),'sha256':sha,'bytes':package.stat().st_size,'files':len(files)}
    (OUT/'RT-v9.1-build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('package','sha256','bytes','files','compile_checks','behavior_checks')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
