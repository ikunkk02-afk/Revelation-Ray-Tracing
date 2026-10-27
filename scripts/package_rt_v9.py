"""Build a verified v9 archive. Installation is handled separately with backups."""
from pathlib import Path
import hashlib,json,zipfile
from rt_source_digest import SHADERS,source_digest
ROOT=SHADERS.parent
OUT=ROOT.parent.parent/'deliverables'
NAME='Revelation-RT-v9-Lighting'

def main():
    digest=source_digest()
    reports={}
    names=['compile-v9.json','material-v9.json','physical-probes-v9.json','seam-v9.json',
           'dense-lights-v9.json','iris-metadata-v9.json']
    for name in names:
        report=json.loads((ROOT/'validation'/name).read_text(encoding='utf-8'))
        assert report['source_digest']==digest,('Stale validation',name)
        assert report.get('passed',all(c['passed'] for c in report.get('checks',[{'passed':False}]))),name
        reports[name]=report
    game=ROOT/'validation/game-smoke-v9.json'
    if game.exists():
        r=json.loads(game.read_text(encoding='utf-8'))
        assert r['source_digest']==digest
        reports[game.name]=r;names.append(game.name)
    old=OUT/'Revelation-RT-v8.3-Performance.zip'
    with zipfile.ZipFile(old) as z:
        changes=[p.relative_to(ROOT).as_posix() for p in sorted(SHADERS.rglob('*')) if p.is_file()
                 and (p.relative_to(ROOT).as_posix() not in z.namelist() or z.read(p.relative_to(ROOT).as_posix())!=p.read_bytes())]
    summary={
        'version':'Revelation RT v9 Lighting','date':'2026-10-27','source_digest':digest,
        'target':'Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1 / RTX 5060 Laptop',
        'default_profile':'Ultra','shader_changes_since_v8_3':changes,
        'compile_checks':len(reports['compile-v9.json']['checks']),
        'material_checks':len(reports['material-v9.json']['tests']),
        'behavior_checks':reports['physical-probes-v9.json']['behavior_checks'],
        'behavior_rays':reports['physical-probes-v9.json']['behavior_rays'],
        'seam_checks':len(reports['seam-v9.json']['tests']),
        'dense_light_checks':len(reports['dense-lights-v9.json']['tests']),
        'controlled_cache_performance':reports['physical-probes-v9.json']['performance'].get('local_diffuse_pipeline'),
        'game_smoke':reports.get('game-smoke-v9.json'),
        'minecraft_same_scene_comparison':False,
        'limitations':['Screen-space diffuse bounce coverage','Local grid geometry coverage',
                       'No DH/Voxy game verification','No guaranteed target FPS','Dense all-light tracing scales with lamp count']}
    (ROOT/'validation/build-v9.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=[p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT/p for p in ('LICENSE','README.md','README.zh-CN.md','docs/RT_V9_LIGHTING.zh-CN.md')]
    files += [ROOT/'validation'/name for name in names+['build-v9.json','seam-v9.png','dense-lights-v9.png']]
    files += [p for p in (ROOT/'scripts').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files=sorted(set(files));OUT.mkdir(exist_ok=True)
    package=OUT/(NAME+'.zip')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes(),str(p)
    sha=hashlib.sha256(package.read_bytes()).hexdigest()
    (OUT/(NAME+'.sha256')).write_text(sha+'  '+package.name+'\n',encoding='utf-8')
    manifest={**summary,'package':str(package),'sha256':sha,'files':len(files),'bytes':package.stat().st_size}
    (OUT/'RT-v9-build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('package','sha256','files','compile_checks','behavior_checks','bytes')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
