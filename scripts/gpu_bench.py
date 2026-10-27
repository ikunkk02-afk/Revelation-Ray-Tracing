"""Timed GPU benchmark for the local-light tracer and its volumetric march.

Dispatches the pack's real functions over a receiver plane with a realistic lamp
count and reports milliseconds per full-HD frame, so each optimisation can be
attributed instead of guessed.

    python scripts/gpu_bench.py [--width 960 --height 540 --frames 12]
"""
from pathlib import Path
import argparse
import json
import re
import zipfile
import ctypes

import glfw
import numpy as np
from OpenGL import GL
from OpenGL.raw.GL.VERSION.GL_3_3 import glGetQueryObjectui64v as get_query_u64

from validate_rt import SHADERS, BASE_MACROS, expand, source, apply_options, profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT = SHADERS.parent
BENCH_OPTIONS = Path(r'D:\HMCL\.minecraft\versions\1.21.1-fabric\shaderpacks'
                     r'\Revelation-RT-v8.2-SeamStartupFix.zip.txt')


def bench_options():
    opts = profile_options('RayTracing')
    if BENCH_OPTIONS.exists():
        for line in BENCH_OPTIONS.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                opts[key] = True if value == 'true' else False if value == 'false' else value
    return opts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=540)
    parser.add_argument('--frames', type=int, default=12)
    parser.add_argument('--lights', type=int, default=12)
    parser.add_argument('--profile', default='RayTracing')
    parser.add_argument('--out', default='validation/gpu-bench.json')
    parser.add_argument('--define', action='append', default=[],
                        help='extra pack option, e.g. RT_LOCAL_TEMPORAL_SHADOWS=true')
    args = parser.parse_args()

    digest = source_digest()
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 6)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(32, 32, 'RT gpu bench', None, None)
    assert window
    glfw.make_context_current(window)

    extra = {}
    for item in args.define:
        key, value = item.split('=', 1)
        extra[key] = True if value == 'true' else False if value == 'false' else value
    pack = {**profile_options(args.profile), **extra}
    options = {**pack, 'RT_LOCAL_SHADOW_SAMPLES': 'testSamples', 'RT_LOCAL_VOLUMETRICS': True}
    shadow_samples = int(pack.get('RT_LOCAL_SHADOW_SAMPLES', 4))
    volume_samples = int(pack.get('RT_LOCAL_VOLUME_SAMPLES', 6))
    half_res = bool(pack.get('RT_LOCAL_HALF_RES', False))
    temporal = bool(pack.get('RT_LOCAL_TEMPORAL_SHADOWS', False))
    header = '#version 460 compatibility\n' + BASE_MACROS + '\nuniform int testSamples;\n'
    for name in ('lib/Utility.glsl', 'lib/universal/Uniform.glsl', 'lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl', 'lib/lighting/BRDF.glsl', 'lib/lighting/LocalLights.glsl',
                 'lib/lighting/LocalVolumetrics.glsl'):
        header += expand(SHADERS / name) + '\n'

    selector = program(source(SHADERS / 'world0/deferred.csh', options))

    bench = program(apply_options(header + '''
layout(local_size_x=8,local_size_y=8) in;
layout(std430,binding=7) writeonly buffer Results {vec4 result[];};
uniform int mode;
void main(){
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy);
    if(any(greaterThanEqual(pixel,ivec2(scaledViewSize))))return;
    vec2 uv=(vec2(pixel)+0.5)*scaledTexelSize;
    vec4 clip=gbufferProjection*vec4(0,0,-6,1);
    vec3 pos=ScreenToViewPos(vec3(uv,clip.z/clip.w*.5+.5));
    pos.z += (uv.x-0.5)*4.0;                      // slanted wall, varied depth
    vec3 n=normalize(vec3(0.15*uv.x,0.1*uv.y,1.0));
    Material material=Material(.55,0,0,vec3(.04),false,false);
    float dither=fract(52.9829189*fract(dot(vec2(pixel),vec2(0.06711056,0.00583715))));
    vec3 d=vec3(0.0),s=vec3(0.0);
    if(mode==0) AddTracedLocalLighting(pos,n,n,material,false,dither,pixel,d,s);
    if(mode==1) d=RTRaymarchLocalFog(vec3(0),pos,dither,pixel)[0];
    if(mode==3) { d=vec3(0.0); }
    if(mode==4) { d=vec3(n.x,0.0,0.0); }      // trivial ALU floor, no lighting
    if(mode==2) {                                  // diffuse only, specular path off
        Material m2=Material(.55,0,0,vec3(.04),false,false); m2.specularMask=false;
        AddTracedLocalLighting(pos,n,n,m2,false,dither,pixel,d,s);
    }
    result[pixel.y*int(scaledViewSize.x)+pixel.x]=vec4(d+s,1);
}
''', options))

    textures = []

    def tex2(unit, data, internal=GL.GL_RGBA32UI, fmt=GL.GL_RGBA_INTEGER, kind=GL.GL_UNSIGNED_INT):
        tex = int(GL.glGenTextures(1)); textures.append(tex)
        GL.glActiveTexture(GL.GL_TEXTURE0 + unit); GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        for pname in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, pname, GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, data.shape[1], data.shape[0], 0, fmt, kind, data)
        return tex

    tex2(0, np.frombuffer((SHADERS / 'texture/rt/scene_shapes.bin').read_bytes(), np.uint32).reshape(1, 4096, 4))
    tex2(1, np.frombuffer((SHADERS / 'texture/rt/scene_alpha.bin').read_bytes(), np.uint32).reshape(-1, 32, 4))
    w, h = args.width, args.height
    tw, th = w // 16, h // 16
    tile_low = tex2(3, np.zeros((th, tw, 4), np.uint32))
    tile_high = tex2(4, np.zeros((th, tw, 4), np.uint32))

    scene = int(GL.glGenTextures(1)); textures.append(scene)
    GL.glActiveTexture(GL.GL_TEXTURE2); GL.glBindTexture(GL.GL_TEXTURE_3D, scene)
    for pname in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
        GL.glTexParameteri(GL.GL_TEXTURE_3D, pname, GL.GL_NEAREST)
    grid = np.zeros((64, 64, 64), np.uint32)
    # A wall of stone in front of the receiver: forces real DDA + shape tests.
    stone = 20000 + 1
    props = (SHADERS / 'block.properties').read_text(encoding='utf-8')
    for i, body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)', props, re.S):
        if 'minecraft:stone' in body.replace('\\', ' ').split():
            stone = int(i) - 20000
            break
    # A finite panel between the receiver (z=-6) and lamps (z=-3..-1),
    # leaving both occluded and unoccluded rays. Never start inside a wall.
    grid[28:29, 29:35, 30:34] = stone
    GL.glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_R32UI, 64, 64, 64, 0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, grid)
    glass = int(GL.glGenTextures(1)); textures.append(glass)
    GL.glActiveTexture(GL.GL_TEXTURE5); GL.glBindTexture(GL.GL_TEXTURE_3D, glass)
    for pname in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
        GL.glTexParameteri(GL.GL_TEXTURE_3D, pname, GL.GL_NEAREST)
    GL.glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_R32UI, 64, 64, 64, 0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, np.zeros((64,64,64),np.uint32))
    hierarchy = int(GL.glGenTextures(1)); textures.append(hierarchy)
    GL.glActiveTexture(GL.GL_TEXTURE6); GL.glBindTexture(GL.GL_TEXTURE_3D, hierarchy)
    for pname in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
        GL.glTexParameteri(GL.GL_TEXTURE_3D, pname, GL.GL_NEAREST)
    GL.glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_RGBA32UI, 16,16,16,0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,None)
    builder = program(source(SHADERS / 'world0/shadowcomp.csh', options))
    GL.glUseProgram(builder)
    for name,unit in (('rtSceneShapesTex',0),('rtSceneGridTex',2),('rtGlassGridTex',5),('rtLocalHierarchyImg',2)):
        GL.glUniform1i(GL.glGetUniformLocation(builder,name),unit)
    GL.glBindImageTexture(2,hierarchy,0,True,0,GL.GL_WRITE_ONLY,GL.GL_RGBA32UI)
    GL.glDispatchCompute(4,4,4); GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)

    buffers = GL.glGenBuffers(2)
    for binding, buffer in zip((5, 7), buffers):
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, binding, int(buffer))
    projection = np.array([[1, 0, 0, 0], [0, 1, 0, 0],
                           [0, 0, -(64 + .1) / (64 - .1), -2 * 64 * .1 / (64 - .1)], [0, 0, -1, 0]], np.float32)

    rng = np.random.default_rng(1234)
    count = args.lights
    lights = np.column_stack((np.linspace(-7, 7, count), rng.uniform(1.5, 4.0, count),
                              rng.uniform(-3.0, -1.0, count), np.full(count, 11))).astype(np.float32)
    data = np.zeros(16 + 256 * 16, np.uint8)
    data[:16] = np.array([len(lights), 0, 0, 0], np.uint32).view(np.uint8)
    values = lights.copy(); values[:, :3] += 32
    data[16:16 + len(values) * 16] = values.view(np.uint8).reshape(-1)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, int(buffers[0]))
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, int(buffers[1]))
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER, w * h * 16, None, GL.GL_DYNAMIC_READ)

    for p_ in (selector, bench):
        GL.glUseProgram(p_)
        for name, unit in (('rtSceneShapesTex', 0), ('rtSceneAlphaTex', 1), ('rtSceneGridTex', 2),
                           ('rtLightTilesTex', 3), ('rtLightTilesHiTex', 4),
                           ('rtLightTilesImg', 0), ('rtLightTilesHiImg', 1)):
            GL.glUniform1i(GL.glGetUniformLocation(p_, name), unit)
        for name, value in (('gbufferModelView', np.eye(4, dtype=np.float32)),
                            ('gbufferModelViewInverse', np.eye(4, dtype=np.float32)),
                            ('gbufferProjection', projection),
                            ('gbufferProjectionInverse', np.linalg.inv(projection))):
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(p_, name), 1, GL.GL_TRUE, value)
        GL.glUniform2f(GL.glGetUniformLocation(p_, 'scaledViewSize'), w, h)
        GL.glUniform2f(GL.glGetUniformLocation(p_, 'scaledTexelSize'), 1 / w, 1 / h)
        GL.glUniform3f(GL.glGetUniformLocation(p_, 'cameraPosition'), 0, 0, 0)
    # Fill the tile masks with the pack's own selector, exactly like the game does.
    GL.glBindImageTexture(0, tile_low, 0, False, 0, GL.GL_WRITE_ONLY, GL.GL_RGBA32UI)
    GL.glBindImageTexture(1, tile_high, 0, False, 0, GL.GL_WRITE_ONLY, GL.GL_RGBA32UI)
    GL.glUseProgram(selector)
    GL.glDispatchCompute((tw + 7) // 8, (th + 7) // 8, 1)
    GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)

    GL.glUseProgram(bench)
    for name, unit in (('rtSceneShapesTex', 0), ('rtSceneAlphaTex', 1), ('rtSceneGridTex', 2),
                       ('rtLightTilesTex', 3), ('rtLightTilesHiTex', 4),('rtGlassGridTex',5),('rtLocalHierarchyTex',6)):
        GL.glUniform1i(GL.glGetUniformLocation(bench, name), unit)
    for name, value in (('gbufferModelView', np.eye(4, dtype=np.float32)),
                        ('gbufferModelViewInverse', np.eye(4, dtype=np.float32)),
                        ('gbufferProjection', projection),
                        ('gbufferProjectionInverse', np.linalg.inv(projection))):
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(bench, name), 1, GL.GL_TRUE, value)
    GL.glUniform2f(GL.glGetUniformLocation(bench, 'scaledViewSize'), w, h)
    GL.glUniform2f(GL.glGetUniformLocation(bench, 'scaledTexelSize'), 1 / w, 1 / h)
    GL.glUniform3f(GL.glGetUniformLocation(bench, 'cameraPosition'), 0, 0, 0)
    GL.glUniform1i(GL.glGetUniformLocation(bench, 'testSamples'), shadow_samples)

    groups = ((w + 7) // 8, (h + 7) // 8, 1)
    queries = [int(np.asarray(GL.glGenQueries(1)).ravel()[0]) for _ in range(2)]

    def time_mode(mode, frames=args.frames):
        GL.glUniform1i(GL.glGetUniformLocation(bench, 'mode'), mode)
        for _ in range(20):                                  # warm up: boost clocks
            GL.glDispatchCompute(*groups)
        GL.glFinish()
        best = None
        for _ in range(3):                                   # min of 3 batches
            GL.glBeginQuery(GL.GL_TIME_ELAPSED, queries[0])
            for _ in range(frames):
                GL.glDispatchCompute(*groups)
            GL.glEndQuery(GL.GL_TIME_ELAPSED)
            GL.glFinish()
            elapsed_ns = ctypes.c_uint64()
            get_query_u64(queries[0], GL.GL_QUERY_RESULT, ctypes.byref(elapsed_ns))
            per_pass = elapsed_ns.value / 1e6 / frames
            best = per_pass if best is None else min(best, per_pass)
        return best                                          # ms per pass

    results = {}
    results['floor_ms'] = time_mode(4)
    results['surface_ms'] = time_mode(0)
    results['fog_ms'] = time_mode(1)
    results['surface_no_specular_ms'] = time_mode(2)
    pixels = w * h
    scale = (2560 * 1494) / pixels
    report = {'renderer': GL.glGetString(GL.GL_RENDERER).decode(),
              'resolution': [w, h], 'lights': count, 'frames': args.frames,
              'shadow_samples': shadow_samples, 'volume_samples': volume_samples, 'half_res': half_res,
              'temporal_shadows': temporal, 'max_traced': pack.get('RT_LOCAL_MAX_TRACED'),
              'volume_light_cap': pack.get('RT_LOCAL_VOLUME_LIGHT_CAP'), 'defines': args.define,
              'ms': results,
              'scope': 'Isolated native-resolution local kernels; not the whole pack or Minecraft FPS. Includes a valid hierarchy and finite blocker panel. GPU timers in nanoseconds converted once to milliseconds.',
              'source_digest': digest}
    print(json.dumps(report, indent=2))
    (ROOT / args.out).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    glfw.destroy_window(window); glfw.terminate()


if __name__ == '__main__':
    main()
