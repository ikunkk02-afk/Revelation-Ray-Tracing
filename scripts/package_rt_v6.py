"""Package v6 reference/performance presets with matching validation reports."""
from pathlib import Path
import difflib, hashlib, json, re, zipfile
from rt_source_digest import source_digest, SHADERS

ROOT=SHADERS.parent
BASE=ROOT.parent.parent
OUT=BASE/'deliverables'


def main():
    digest=source_digest()
    compile_report=json.loads((ROOT/'validation/compile-v6.json').read_text())
    probe_report=json.loads((ROOT/'validation/physical-probes-v6.json').read_text())
    assert compile_report['source_digest']==probe_report['source_digest']==digest,'Stale reports'
    assert compile_report['checks'] and all(t['passed'] for t in compile_report['checks'])
    assert probe_report['passed'] and all(t['passed'] for t in probe_report['tests'])
    iris_report=json.loads((ROOT/'validation/iris-metadata-v6.json').read_text())
    assert iris_report['passed'] and iris_report['source_digest']==digest,'Stale Iris metadata report'
    visited=set();references=0
    def includes(path):
        nonlocal references
        if path in visited:return
        visited.add(path)
        for inc in re.findall(r'^\s*#include\s+"([^"]+)"',path.read_text(encoding='utf-8'),re.M):
            target=(SHADERS/inc.lstrip('/')) if inc.startswith('/') else path.parent/inc
            assert target.is_file(),(path,inc)
            references+=1;includes(target.resolve())
    for path in SHADERS.rglob('*'):
        # Validate the render entrypoint include graph. Unreferenced legacy
        # utility implementations are not shader programs scheduled by Iris.
        if path.suffix in ('.glsl','.csh','.vsh','.fsh'):includes(path.resolve())
    props=(SHADERS/'shaders.properties').read_text()
    assert 'allowConcurrentCompute = false' in props
    assert 'SkyView.comp' in (SHADERS/'world0/begin.csh').read_text()
    assert 'program.world0/begin.enabled' not in props
    assert 'customTexture.rtSceneAlphaTex' in props
    assert 'distance < 8.0' not in (SHADERS/'lib/lighting/LocalLights.glsl').read_text()
    assert 'BuildLocalHierarchy.comp' in (SHADERS/'world0/shadowcomp.csh').read_text()
    assert 'RTTraceLocalVisibility(origin,target)' in (SHADERS/'lib/lighting/LocalLights.glsl').read_text()
    assert probe_report['performance']['baseline_functions_match_v5'] is True
    assert (SHADERS/'texture/rt/scene_shapes.bin').stat().st_size==4096*16
    ids=list(map(int,re.findall(r'^block\.(\d+)\s*=',(SHADERS/'block.properties').read_text(),re.M)))
    assert max(ids)<32768 and len(ids)==len(set(ids))
    report={'version':'RT v6 Reference / Performance','date':'2026-10-26','target':'Minecraft 1.21.1 Fabric / Iris 1.8.14-beta.1',
            'source_digest':digest,'renderer':compile_report['renderer'],
            'compile_link_checks':len(compile_report['checks']),'behavior_checks':probe_report['behavior_checks'],
            'cutout_rays':probe_report['cutout_rays'],'behavior_rays':probe_report['behavior_rays'],'iris_metadata':True,'include_references_checked':references,
            'runtime_game_validation':False,'performance_measured':False,'gpu_kernel_performance_measured':True,
            'gpu_visibility_benchmarks':probe_report['performance']['scenes'],
            'excluded_integrations':compile_report['excluded_integrations'],
            'model_capture':json.loads((ROOT/'validation/scene-models.json').read_text())}
    (ROOT/'validation/build-v6.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    OUT.mkdir(exist_ok=True)
    files=[p for p in SHADERS.rglob('*') if p.is_file()]
    for path in ('LICENSE','README.md','README.zh-CN.md','docs/RT_V6_REFERENCE.zh-CN.md',
                 'validation/build-v6.json','validation/compile-v6.json','validation/physical-probes-v6.json',
                 'validation/iris-metadata-v6.json','validation/scene-models.json','validation/performance-v6.json','validation/v6-aperture-probe.png',
                 'scripts/generate_rt_scene.py','scripts/rt_alpha_geometry.py','scripts/data/block-material-base.properties',
                 'scripts/data/rt-alpha-selectors.json','scripts/probe_rt_v6.py','scripts/validate_rt_v6.py','scripts/local_ray_v6_checks.py',
                 'scripts/validate_rt.py','scripts/validate_rt_glass.py','scripts/IrisMetadataCheck.java','scripts/check_iris_metadata.py',
                 'scripts/rt_source_digest.py','scripts/package_rt_v6.py','scripts/requirements-rt-validation.txt'):
        files.append(ROOT/path)
    files += [p for p in (ROOT/'docs').rglob('*') if p.is_file()]
    files=list(dict.fromkeys(files))
    package=OUT/'Revelation-RT-v6-Reference.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        for p in files:assert z.read(p.relative_to(ROOT).as_posix())==p.read_bytes(),p
    changed=[];patch=[]
    with zipfile.ZipFile(OUT/'Revelation-RT-v5-Realistic.zip') as old:
        for p in files:
            name=p.relative_to(ROOT).as_posix();data=p.read_bytes()
            previous=old.read(name) if name in old.namelist() else b''
            if previous==data:continue
            changed.append({'path':name,'status':'modified' if previous else 'added','sha256':hashlib.sha256(data).hexdigest()})
            if p.suffix in ('.glsl','.frag','.vert','.comp','.properties','.py','.java','.txt','.md','.lang'):
                patch.extend(difflib.unified_diff(previous.decode('utf-8-sig').splitlines(True),data.decode('utf-8-sig').splitlines(True),fromfile='a/'+name,tofile='b/'+name))
    (OUT/'Revelation-RT-v6-source.patch').write_text(''.join(patch),encoding='utf-8',newline='\n')
    sha=hashlib.sha256(package.read_bytes()).hexdigest()
    manifest={**report,'package':package.name,'sha256':sha,'bytes':package.stat().st_size,'files':len(files),'changes':changed}
    (OUT/'RT-v6-build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (OUT/'Revelation-RT-v6-Reference.sha256').write_text(sha+'  '+package.name+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('changes','model_capture')},indent=2))

if __name__=='__main__':main()
