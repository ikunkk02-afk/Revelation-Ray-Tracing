"""Build validated v9.3 light controls without installing or launching Minecraft."""
import hashlib,json,zipfile
from rt_source_digest import SHADERS,source_digest

ROOT=SHADERS.parent;OUT=ROOT.parent.parent/'deliverables';NAME='Revelation-RT-v9.3-LightControls'

def main():
    digest=source_digest();reports={}
    for name in ('compile-v93.json','physical-probes-v93.json','iris-metadata-v93.json',
                 'light-controls-v93.json','shadow-projection-v93.json','seam-v93.json','dense-lights-v93.json'):
        r=json.loads((ROOT/'validation'/name).read_text(encoding='utf-8'))
        assert r['source_digest']==digest,('Stale report',name)
        assert r.get('passed',bool(r.get('checks')) and all(c['passed'] for c in r.get('checks',[]))),name
        reports[name]=r
    with zipfile.ZipFile(OUT/'Revelation-RT-v9.2-SingleProjection.zip') as old:
        changed=[p.relative_to(ROOT).as_posix() for p in sorted(SHADERS.rglob('*')) if p.is_file() and
                 (p.relative_to(ROOT).as_posix() not in old.namelist() or old.read(p.relative_to(ROOT).as_posix())!=p.read_bytes())]
    summary=dict(version='Revelation RT v9.3 Light Controls',date='2026-10-27',source_digest=digest,
                 baseline='Revelation-RT-v9.2-SingleProjection.zip',changed_shader_files=changed,default_profile='Ultra',
                 compile_checks=len(reports['compile-v93.json']['checks']),
                 behavior_checks=reports['physical-probes-v93.json']['behavior_checks'],
                 behavior_rays=reports['physical-probes-v93.json']['behavior_rays'],
                 light_controls_checks=len(reports['light-controls-v93.json']['tests']),
                 projection_checks=len(reports['shadow-projection-v93.json']['tests']),
                 minecraft_launched=False,minecraft_fps_measured=False,
                 defaults={'custom_block_color':False,'custom_held_color':False,'flashlight':False,
                           'beam_full_angle_degrees':40,'beam_edge_softness':.2,'beam_range_blocks':24},
                 feature_scope='Independent placed/held brightness and color, emission/GI tint, torch-only camera-centred spotlight with original collision-constrained shadow source; stable single shadow ray retained')
    build=ROOT/'validation/build-v93.json';build.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    files=[p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT/p for p in ('LICENSE','README.md','README.zh-CN.md','docs/RT_V9_2_PROJECTION.zh-CN.md','docs/RT_V9_3_LIGHT_CONTROLS.zh-CN.md')]
    files += [ROOT/'validation'/name for name in reports]
    files += [build,ROOT/'validation/shadow-projection-v93.png',ROOT/'validation/seam-v93.png',ROOT/'validation/dense-lights-v93.png']
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
    (OUT/'RT-v9.3-build-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('package','sha256','bytes','files','compile_checks','behavior_checks','light_controls_checks')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
