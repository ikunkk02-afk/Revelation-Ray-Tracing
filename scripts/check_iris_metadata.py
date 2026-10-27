"""Run the installed Iris parser with local dependencies, without Minecraft."""
import argparse, hashlib, json, os, shutil, subprocess
from pathlib import Path
from rt_source_digest import SHADERS, source_digest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iris',type=Path,required=True)
    parser.add_argument('--libraries',type=Path,required=True)
    parser.add_argument('--report-name',default='iris-metadata-v5.json')
    args=parser.parse_args()
    assert '1.8.14-beta.1+mc1.21.1' in args.iris.name,'This metadata checker targets the installed 1.8.14-beta.1 version'
    deps=[args.iris]
    for name in ('guava-33.3.1-jre.jar','joml-1.10.5.jar','slf4j-api-2.0.9.jar','fastutil-8.5.12.jar'):
        deps.append(next(args.libraries.rglob(name)))
    java_bin=Path(shutil.which('javap')).parent
    classes=SHADERS.parent/'validation/iris-classes-v5'
    classes.mkdir(exist_ok=True)
    cp=os.pathsep.join(str(p) for p in deps)
    digest=source_digest()
    subprocess.run([str(java_bin/'javac.exe'),'--release','21','-cp',cp,'-d',str(classes),str(Path(__file__).with_name('IrisMetadataCheck.java'))],check=True)
    result=subprocess.run([str(java_bin/'java.exe'),'-cp',cp+os.pathsep+str(classes),'IrisMetadataCheck',str(SHADERS)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:
        print(result.stdout+result.stderr)
        raise SystemExit(result.returncode)
    assert digest==source_digest(),'Sources changed during metadata check'
    report={'passed':True,'source_digest':digest,'iris_jar':args.iris.name,'iris_jar_sha256':hashlib.sha256(args.iris.read_bytes()).hexdigest(),
            'scope':'Installed Iris metadata and option discovery; no game pipeline creation','output':result.stdout.strip()}
    (SHADERS.parent/'validation'/args.report_name).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(result.stdout.strip())

if __name__=='__main__':main()
