import argparse, functools, hashlib, json, sys
from pathlib import Path

import glfw
from OpenGL import GL

from validate_rt import SHADERS, source as base_source, profile_options
import validate_rt as rt_shared
from rt_source_digest import source_digest
# Source files stay immutable throughout a checked run. Cache expanded includes
# so repeated profiles and fingerprinting do not repeatedly read the same tree.
_uncached_expand=rt_shared.expand
@functools.cache
def _expanded_file(path):return _uncached_expand(path)
rt_shared.expand=lambda path,stack=():_expanded_file(path)
REPORT_DIR=SHADERS.parent/'validation'
BRANCHES={
    'glass_grid_off':{'RT_GLASS_ENABLED':False},
    'physical_glass_off':{'RT_PHYSICAL_GLASS':False},
    'all_local_off':{'RT_LOCAL_LIGHTS':False,'RT_HANDHELD_SHADOWS':False,'RT_GLASS_ENABLED':False},
    'refraction_trace':{'RAYTRACED_REFRACTION':True},
    'PBR':{'RP_SUPPORT':True,'MOD_BLOCK_SUPPORT':True},
    'cached_local':{'RT_LOCAL_HALF_RES':True},
    'HDR':{'HDR_ENABLED':True},
    'acceleration_off':{'RT_LOCAL_ACCELERATION':False},
    'handheld_only':{'RT_LOCAL_LIGHTS':False,'RT_GLASS_ENABLED':False},
    'glass_only':{'RT_LOCAL_LIGHTS':False,'RT_HANDHELD_SHADOWS':False},
    'PBR_cached_local':{'RP_SUPPORT':True,'MOD_BLOCK_SUPPORT':True,'RT_LOCAL_HALF_RES':True},
    'native_local':{'RT_LOCAL_HALF_RES':False},
    'analytic_local':{'RT_LOCAL_TRACED_SHADOWS':False},
    'traced_volume':{'RT_LOCAL_VOLUMETRICS':True},
    'temporal_local':{'RT_LOCAL_SOFT_SHADOWS':True,'RT_LOCAL_SHADOW_SAMPLES':'4','RT_LOCAL_TEMPORAL_SHADOWS':True},
    'fixed_area':{'RT_LOCAL_SOFT_SHADOWS':True,'RT_LOCAL_SHADOW_SAMPLES':'4'},
    'hard_local':{'RT_LOCAL_SOFT_SHADOWS':False,'RT_LOCAL_TEMPORAL_SHADOWS':True},
    'custom_lights':{'RT_BLOCK_CUSTOM_COLOR':True,'HELD_LIGHT_CUSTOM_COLOR':True},
    'flashlight':{'RT_HANDHELD_FLASHLIGHT':True},
    'flashlight_custom':{'RT_HANDHELD_FLASHLIGHT':True,'RT_BLOCK_CUSTOM_COLOR':True,'HELD_LIGHT_CUSTOM_COLOR':True},
    'hand_color_sampling':{'COLORED_HANDHELD_LIGHTING':True,'HELD_LIGHT_CUSTOM_COLOR':False},
    'lights_zero':{'BLOCKLIGHT_BRIGHTNESS':'0.0','HELD_LIGHT_BRIGHTNESS':'0.0','RT_HANDHELD_FLASHLIGHT':True},
}

def options_for(variant):
    return {**profile_options('RayTracing'),**BRANCHES[variant]} if variant in BRANCHES else profile_options(variant)

def source(path,options):
    text=base_source(path,options)
    # HDR_ENABLED is supplied by Iris, rather than an option in Setting.glsl.
    if options.get('HDR_ENABLED'):
        text=text.replace('#define IS_IRIS','#define HDR_ENABLED\n#define IS_IRIS')
    return text

def fingerprint(path,options):
    mode='v81-nonseparable-compute' if path.suffix=='.csh' else 'v6-source-cache-1'
    text=mode+';MC_RENDER_STAGE_OUTLINE=14\n'+source(path,options)
    if path.suffix=='.vsh':text+=source(path.with_suffix('.fsh'),options)
    return hashlib.sha256(text.encode()).hexdigest()

FILES = [
    ('world0', 'begin.csh'), ('world0', 'begin_a.csh'), ('world0', 'begin1.csh'), ('world0', 'begin2.csh'),
    ('world0', 'deferred.csh'), ('world0', 'deferred1.csh'), ('world0', 'deferred1_a.csh'),
    ('world0', 'deferred4.fsh'), ('world0', 'deferred21.fsh'), ('world0', 'deferred50.fsh'),
    ('world0', 'composite2.fsh'), ('world0', 'composite2.csh'), ('world0', 'composite.fsh'),
    ('world0', 'composite1.csh'), ('world0', 'final.fsh'),
    ('world0', 'shadow.vsh'), ('world0', 'shadow.fsh'),
    ('world0', 'gbuffers_terrain.vsh'), ('world0', 'gbuffers_block.vsh'), ('world0', 'gbuffers_water.vsh'),
    ('world0', 'gbuffers_hand.vsh'), ('world0', 'gbuffers_hand.fsh'),
    ('world0', 'deferred2.csh'), ('world0', 'deferred3.fsh'), ('world0', 'deferred5.csh'),
    ('world0', 'deferred6.csh'), ('world0', 'deferred7.csh'), ('world0', 'deferred8.csh'),
    ('world0', 'deferred9.csh'), ('world0', 'deferred10.csh'),
    ('world-1', 'begin.csh'), ('world-1', 'begin_a.csh'), ('world-1', 'begin1.csh'), ('world-1', 'begin2.csh'),
    ('world-1', 'deferred.csh'), ('world-1', 'deferred1.csh'), ('world-1', 'deferred4.fsh'),
    ('world-1', 'deferred21.fsh'), ('world-1', 'deferred50.fsh'), ('world-1', 'composite2.fsh'),
    ('world-1', 'composite2.csh'), ('world-1', 'final.fsh'),
    ('world-1', 'shadow.vsh'), ('world-1', 'gbuffers_terrain.vsh'), ('world-1', 'gbuffers_block.vsh'),
]

STAGE = {'.csh': GL.GL_COMPUTE_SHADER, '.fsh': GL.GL_FRAGMENT_SHADER, '.vsh': GL.GL_VERTEX_SHADER}


def compile_one(path: Path, options, as_separable=True):
    shader = GL.glCreateShader(STAGE[path.suffix])
    text = source(path, options)
    text = text.replace('#define IS_IRIS', '#define MC_RENDER_STAGE_OUTLINE 14\n#define IS_IRIS')
    GL.glShaderSource(shader, text)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader)
        if isinstance(log, bytes):
            log = log.decode('utf-8', 'replace')
        (REPORT_DIR/'failed_shader.glsl').write_text(text, encoding='utf-8')
        return False, f'{path} COMPILE FAIL: {log}'
    program = GL.glCreateProgram()
    GL.glAttachShader(program, shader)
    pair = None
    if path.suffix == '.vsh':
        pair = GL.glCreateShader(GL.GL_FRAGMENT_SHADER)
        GL.glShaderSource(pair, source(path.with_suffix('.fsh'), options))
        GL.glCompileShader(pair)
        if not GL.glGetShaderiv(pair, GL.GL_COMPILE_STATUS):
            log = GL.glGetShaderInfoLog(pair)
            if isinstance(log, bytes):
                log = log.decode('utf-8', 'replace')
            return False, f'{path.with_suffix(".fsh")} COMPILE FAIL: {log}'
        GL.glAttachShader(program, pair)
    elif path.suffix != '.csh':
        GL.glProgramParameteri(program, GL.GL_PROGRAM_SEPARABLE, GL.GL_TRUE)
    GL.glLinkProgram(program)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(program)
        if isinstance(log, bytes):
            log = log.decode('utf-8', 'replace')
        return False, f'{path} LINK FAIL: {log}'
    GL.glDeleteProgram(program)
    GL.glDeleteShader(shader)
    if pair:
        GL.glDeleteShader(pair)
    return True, ''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report-name',default='compile-v8.json')
    parser.add_argument('--stamp-cache',action='store_true')
    args=parser.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    digest_before=source_digest()
    report_path=REPORT_DIR/args.report_name
    if not report_path.exists():
        report_path.write_text((REPORT_DIR/'compile-v71.json').read_text(),encoding='utf-8')
    old=json.loads(report_path.read_text()) if report_path.exists() else {}
    if args.stamp_cache:
        assert old.get('source_digest')==digest_before,'Cannot stamp a stale report'
        for check in old['checks']:check['source_hash']=fingerprint(SHADERS/check['file'],options_for(check['variant']))
        assert source_digest()==digest_before,'Sources changed during cache stamping'
        report_path.write_text(json.dumps(old,indent=2)+'\n',encoding='utf-8')
        print('Stamped exact-source cache from matching validated tree',flush=True)
        return
    checks = []
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 6)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(32, 32, 'v6 compile', None, None)
    assert window
    glfw.make_context_current(window)
    renderer = GL.glGetString(GL.GL_RENDERER)
    if isinstance(renderer, bytes):
        renderer = renderer.decode('utf-8', 'replace')
    cache={(c['variant'],c['file']):c.get('source_hash') for c in old.get('checks',[]) if c['passed']} if old.get('renderer')==renderer else {}

    # Affected RT passes and their producers/consumers; optional renderer
    # integrations need their own injected interfaces and are excluded here.
    entries = [SHADERS/world/name for world,name in FILES if (SHADERS/world/name).exists()]
    entries += [SHADERS/world/name for world in ('world0','world-1')
                for name in ('gbuffers_water.vsh','gbuffers_hand_water.vsh','composite2.csh','shadowcomp.csh','composite.fsh')
                if (SHADERS/world/name).exists()]
    entries += [SHADERS/w/n for w in ('world0','world-1') for n in ('deferred18.csh','deferred20.csh','gbuffers_basic.vsh','composite31.fsh')]
    entries += [SHADERS/'world1'/n for n in ('gbuffers_terrain.vsh','deferred21.fsh','final.fsh','deferred50.fsh')]
    entries=[p for p in dict.fromkeys(entries) if p.exists()]
    for variant in ('Default','Low','Medium','High','Ultra','RayTracing'):
        options = profile_options(variant)
        for path in entries:
            print(f'checking {variant}: {path.parent.name}/{path.name}',flush=True)
            signature=fingerprint(path,options)
            reused=cache.get((variant,str(path.relative_to(SHADERS))))==signature
            ok,message=(True,'') if reused else compile_one(path,options)
            if not ok:
                print(f'[{variant}] {message}', flush=True)
                glfw.destroy_window(window)
                glfw.terminate()
                sys.exit(1)
            checks.append({'variant':variant,'file':str(path.relative_to(SHADERS)),'passed':True,'source_hash':signature,'reused_exact_source':reused})
        print(f'compiled {variant}', flush=True)

    # Option combinations that cross different include/resource branches.
    critical = [('world0','composite2.csh'),('world0','composite2.fsh'),('world0','shadow.vsh'),
                ('world0','gbuffers_water.vsh'),('world0','deferred21.fsh'),('world-1','composite2.csh'),('world0','shadowcomp.csh'),('world0','composite.fsh'),('world0','deferred18.csh'),('world0','deferred20.csh'),('world0','deferred50.fsh'),('world0','gbuffers_basic.vsh'),('world0','composite31.fsh'),('world0','final.fsh')]
    for variant,overrides in BRANCHES.items():
        options={**profile_options('RayTracing'),**overrides}
        print('checking branch '+variant,flush=True)
        for dimension,name in critical:
            path=SHADERS/dimension/name
            signature=fingerprint(path,options)
            reused=cache.get((variant,str(path.relative_to(SHADERS))))==signature
            ok,message=(True,'') if reused else compile_one(path,options)
            if not ok: raise RuntimeError(f'{variant}: {message}')
            checks.append({'variant':variant,'file':str(path.relative_to(SHADERS)),'passed':True,'source_hash':signature,'reused_exact_source':reused})
    assert source_digest()==digest_before,'Shader sources changed during validation; rerun required'
    report_path.write_text(
        json.dumps({'source_digest':digest_before,'renderer':renderer,'coverage':'RT v8: six quality presets, all-light masks/direct/volume, original lighting branches, handheld/glass/cache regression','excluded_integrations':['Distant Horizons','Voxy'], 'checks':checks},indent=2),encoding='utf-8')
    print(f'PASS {len(checks)} checks on {renderer}', flush=True)
    glfw.destroy_window(window)
    glfw.terminate()


if __name__=='__main__':main()
