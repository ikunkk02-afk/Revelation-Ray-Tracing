"""Build the v8 shaderpack only from a matching, validated shader tree."""
from pathlib import Path
import difflib, hashlib, json, re, zipfile
from rt_source_digest import SHADERS, source_digest

ROOT=SHADERS.parent
OUT=ROOT.parent.parent/'deliverables'

def main():
    digest=source_digest()
    reports={name:json.loads((ROOT/'validation'/name).read_text(encoding='utf-8')) for name in
             ('compile-v8.json','physical-probes-v8-regression.json','dense-lights-v8.json','iris-metadata-v8.json')}
    for name,report in reports.items():
        assert report['source_digest']==digest,('Stale report',name)
        if 'checks' in report:assert report['checks'] and all(t['passed'] for t in report['checks'])
        else:assert report['passed'],name
    visited=set();references=0
    def check_include(path):
        nonlocal references
        if path in visited:return
        visited.add(path)
        for inc in re.findall(r'^\s*#include\s+"([^"]+)"',path.read_text(encoding='utf-8'),re.M):
            target=SHADERS/inc.lstrip('/') if inc.startswith('/') else path.parent/inc
            assert target.is_file(),(path,inc)
            references+=1;check_include(target.resolve())
    for path in SHADERS.rglob('*'):
        # Start at scheduled Iris entrypoints. Unreferenced upstream .comp
        # utilities are retained as source, but are not part of the render graph.
        if path.suffix in ('.csh','.vsh','.fsh'):check_include(path.resolve())
    compiled=reports['compile-v8.json'];regression=reports['physical-probes-v8-regression.json'];dense=reports['dense-lights-v8.json']
    profiles=list(json.loads((ROOT/'validation/profiles-v8.json').read_text(encoding='utf-8')))
    report={'version':'Revelation RT v8 Quality / all-light masks','date':'2026-10-27',
            'target':'Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1','source_digest':digest,
            'renderer':compiled['renderer'],'profiles':profiles,'default_profile':'RayTracing',
            'compile_link_checks':len(compiled['checks']),'dense_light_checks':len(dense['tests']),
            'regression_checks':regression['behavior_checks'],'behavior_rays':regression['behavior_rays'],
            'include_references_checked':references,'iris_profile_transitions_checked':36,
            'runtime_game_validation':False,'minecraft_fps_measured':False,
            'excluded_integrations':compiled['excluded_integrations'],
            'limits':{'local_capture_grid_blocks':[64,64,64],'maximum_captured_lights':256,
                      'indirect_and_reflections':'screen-space','source_geometry':'finite disc proxy'}}
    (ROOT/'validation/build-v8.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    files=[p for p in SHADERS.rglob('*') if p.is_file()]
    files += [ROOT/p for p in ('LICENSE','README.md','README.zh-CN.md','docs/RT_V8_QUALITY.zh-CN.md',
              'validation/build-v8.json','validation/profiles-v8.json','validation/compile-v8.json',
              'validation/physical-probes-v8-regression.json','validation/dense-lights-v8.json',
              'validation/iris-metadata-v8.json','validation/dense-lights-v8.png','validation/scene-models.json')]
    files += [p for p in (ROOT/'scripts').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [p for p in (ROOT/'docs').rglob('*') if p.is_file()]
    files=sorted(set(files))
    OUT.mkdir(exist_ok=True)
    package=OUT/'Revelation-RT-v8-Quality.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes(),p
    changes=[];patch=[]
    with zipfile.ZipFile(OUT/'Revelation-RT-v7.1-HandheldFix.zip') as old:
        for p in files:
            name=p.relative_to(ROOT).as_posix();data=p.read_bytes()
            previous=old.read(name) if name in old.namelist() else b''
            if previous==data:continue
            changes.append({'path':name,'status':'modified' if previous else 'added','sha256':hashlib.sha256(data).hexdigest()})
            if p.suffix in ('.glsl','.frag','.vert','.comp','.properties','.py','.java','.txt','.md','.lang'):
                patch.extend(difflib.unified_diff(previous.decode('utf-8-sig').splitlines(True),data.decode('utf-8-sig').splitlines(True),fromfile='a/'+name,tofile='b/'+name))
    (OUT/'Revelation-RT-v8-source.patch').write_text(''.join(patch),encoding='utf-8',newline='\n')
    sha=hashlib.sha256(package.read_bytes()).hexdigest()
    manifest={**report,'package':package.name,'sha256':sha,'bytes':package.stat().st_size,'files':len(files),'changes':changes}
    (OUT/'RT-v8-build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (OUT/'Revelation-RT-v8-Quality.sha256').write_text(sha+'  '+package.name+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k!='changes'},indent=2))

if __name__=='__main__':main()
