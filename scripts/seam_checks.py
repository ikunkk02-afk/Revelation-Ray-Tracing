"""Tile-seam regression for the 16x16 local-light mask.

Reported symptom: at the junction of several lamps the shading breaks into
chains of 16 px blocks. The shipped v7.1 selector kept the nearest four lights
per tile, so neighbouring tiles integrated different light sets.

This test keeps that selector as a failing control, then asserts for the
current tree that

  1. every tile's mask is a strict superset of the lights that actually
     contribute to pixels inside that tile (conservativity),
  2. mask-driven integration equals exhaustive integration,
  3. no discontinuity appears on the 16 px tile grid (seam ratio),
  4. local volumetric in-scattering is continuous across tile borders.

No Minecraft is launched; the receiver is a controlled GPU plane.
"""
from pathlib import Path
import argparse
import json
import re
import zipfile

import glfw
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw

from validate_rt import SHADERS, BASE_MACROS, expand, source, apply_options, profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT = SHADERS.parent
TILE = 16


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-name', default='seam-v8.json')
    parser.add_argument('--preview-name', default='seam-v8.png')
    args = parser.parse_args()
    digest = source_digest()

    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 6)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(32, 32, 'RT tile seam regression', None, None)
    assert window
    glfw.make_context_current(window)

    # The shipped default is the analytic (untraced) local-light path; the tile
    # mask must be exact there, so this regression runs without the trace budget.
    options = {**profile_options('RayTracing'), 'RT_GLASS_ENABLED': False, 'RT_LOCAL_VOLUMETRICS': True, 'RT_LOCAL_SOFT_SHADOWS': True,
               'RT_LOCAL_ACCELERATION': False, 'RT_LOCAL_SHADOW_SAMPLES': 'testSamples',
               'RT_LOCAL_TRACED_SHADOWS': False, 'RT_LOCAL_TEMPORAL_SHADOWS': False}
    selector = program(source(SHADERS / 'world0/deferred.csh', options))
    header = '#version 460 compatibility\n' + BASE_MACROS + '\nuniform int testSamples;\n'
    for name in ('lib/Utility.glsl', 'lib/universal/Uniform.glsl', 'lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl', 'lib/lighting/BRDF.glsl', 'lib/lighting/LocalLights.glsl',
                 'lib/lighting/LocalVolumetrics.glsl'):
        header += expand(SHADERS / name) + '\n'
    with zipfile.ZipFile(ROOT.parent.parent / 'deliverables/Revelation-RT-v7.1-HandheldFix.zip') as z:
        old = z.read('shaders/lib/lighting/LocalLights.glsl').decode('utf-8')
    old = re.sub(r'^\s*#include\s+"([^"]+)"\s*$', lambda m: expand(SHADERS / m[1].lstrip('/')), old, flags=re.M)
    old = old.replace('RT_LOCAL_LIGHTING', 'RT_LOCAL_LIGHTING_OLD').replace('AddTracedLocalLighting', 'AddOldLocalLighting')
    header += ('uniform usampler2D rtOldTilesTex;\n'
               'uvec4 RTLightIndices(ivec2 pixel) {return texelFetch(rtOldTilesTex,'
               'clamp(pixel/16,ivec2(0),textureSize(rtOldTilesTex,0)-1),0);}\n') + old
    shader = program(apply_options(header + '''
layout(local_size_x=8,local_size_y=8) in;
layout(std430,binding=7) writeonly buffer Results {vec4 result[];};
uniform int mode;
uniform int only;
void main(){
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy);
    if(any(greaterThanEqual(pixel,ivec2(scaledViewSize))))return;
    vec2 uv=(vec2(pixel)+0.5)*scaledTexelSize;
    vec4 clip=gbufferProjection*vec4(0,0,-4,1);
    vec3 pos=ScreenToViewPos(vec3(uv,clip.z/clip.w*.5+.5));
    // Slight tilt so neighbouring tiles see different receiver depth, the way a
    // real wall does; keeps the shipped v7.1 control on its five depth probes.
    pos.z += (uv.x-0.5)*1.2;
    vec3 n=vec3(0,0,1),d=vec3(0),s=vec3(0);
    Material material=Material(.5,0,0,vec3(.04),false,false);
    float dither = fract(52.9829189*fract(dot(gl_GlobalInvocationID.xy,vec2(0.06711056,0.00583715))));
    if(mode==0) AddTracedLocalLighting(pos,n,n,material,false,dither,pixel,d,s);
    if(mode==1) {
        vec3 player=transMAD(gbufferModelViewInverse,pos);
        for(uint i=0u;i<min(rtScene.lightCount,rtMaxLights);++i)
            RTIntegrateLocalEmitter(i,player,player+n*max(.008,abs(pos.z)*8e-5),n,n,normalize(-pos),material,dither,d,s);
    }
    if(mode==2) AddOldLocalLighting(pos,n,n,material,false,dither,pixel,d,s);
    if(mode==3) d=RTRaymarchLocalFog(vec3(0),pos,dither,pixel)[0];
    if(mode==4) {
        vec3 player=transMAD(gbufferModelViewInverse,pos);
        RTIntegrateLocalEmitter(uint(only),player,player+n*max(.008,abs(pos.z)*8e-5),n,n,normalize(-pos),material,dither,d,s);
    }
    result[pixel.y*int(scaledViewSize.x)+pixel.x]=vec4(d,1);
}
''', options))

    textures = []

    def tex2(unit, data, internal=GL.GL_RGBA32UI, fmt=GL.GL_RGBA_INTEGER, kind=GL.GL_UNSIGNED_INT):
        tex = int(GL.glGenTextures(1)); textures.append(tex)
        GL.glActiveTexture(GL.GL_TEXTURE0 + unit); GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, internal, data.shape[1], data.shape[0], 0, fmt, kind, data)
        return tex

    tex2(0, np.frombuffer((SHADERS / 'texture/rt/scene_shapes.bin').read_bytes(), np.uint32).reshape(1, 4096, 4))
    tex2(1, np.frombuffer((SHADERS / 'texture/rt/scene_alpha.bin').read_bytes(), np.uint32).reshape(-1, 32, 4))
    scene = int(GL.glGenTextures(1)); textures.append(scene)
    GL.glActiveTexture(GL.GL_TEXTURE2); GL.glBindTexture(GL.GL_TEXTURE_3D, scene)
    GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_3D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST)
    grid = np.zeros((64, 64, 64), np.uint32)
    GL.glTexImage3D(GL.GL_TEXTURE_3D, 0, GL.GL_R32UI, 64, 64, 64, 0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT, grid)
    buffers = GL.glGenBuffers(2)
    for binding, buffer in zip((5, 7), buffers):
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER, binding, int(buffer))
    projection = np.array([[1, 0, 0, 0], [0, 1, 0, 0],
                           [0, 0, -(64 + .1) / (64 - .1), -2 * 64 * .1 / (64 - .1)], [0, 0, -1, 0]], np.float32)

    tests = []

    def check(name, ok, **details):
        tests.append(dict(name=name, passed=bool(ok), **details))
        print(('PASS ' if ok else 'FAIL ') + name + ' ' + json.dumps(details), flush=True)

    def set_lights(lights):
        data = np.zeros(16 + 256 * 16, np.uint8)
        data[:16] = np.array([len(lights), 0, 0, 0], np.uint32).view(np.uint8)
        values = np.array(lights, np.float32).copy(); values[:, :3] += 32
        data[16:16 + len(values) * 16] = values.view(np.uint8).reshape(-1)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, int(buffers[0]))
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER, data.nbytes, data, GL.GL_DYNAMIC_DRAW)

    state = {}

    def setup(width, height, lights, camera=(0, 0, 0)):
        tw, th = max(width // TILE, 1), max(height // TILE, 1)
        low = tex2(3, np.zeros((th, tw, 4), np.uint32))
        high = tex2(4, np.zeros((th, tw, 4), np.uint32))
        oldtiles = np.zeros((th, tw, 4), np.uint32)
        for y in range(th):
            for x in range(tw):
                receiver = np.array([((min(x * TILE + 8, width - 1) + .5) / width * 2 - 1) * 4,
                                     ((min(y * TILE + 8, height - 1) + .5) / height * 2 - 1) * 4, -4])
                order = np.argsort(np.sum((np.array(lights)[:, :3] - receiver) ** 2, axis=1), kind='stable')[:4] + 1
                oldtiles[y, x, :len(order)] = order
        old = tex2(5, oldtiles)
        for p in (selector, shader):
            GL.glUseProgram(p)
            for name, unit in (('rtSceneShapesTex', 0), ('rtSceneAlphaTex', 1), ('rtSceneGridTex', 2),
                               ('rtLightTilesTex', 3), ('rtLightTilesHiTex', 4), ('rtOldTilesTex', 5),
                               ('rtLightTilesImg', 0), ('rtLightTilesHiImg', 1)):
                GL.glUniform1i(GL.glGetUniformLocation(p, name), unit)
            for name, value in (('gbufferModelView', np.eye(4, dtype=np.float32)),
                                ('gbufferModelViewInverse', np.eye(4, dtype=np.float32)),
                                ('gbufferProjection', projection),
                                ('gbufferProjectionInverse', np.linalg.inv(projection))):
                GL.glUniformMatrix4fv(GL.glGetUniformLocation(p, name), 1, GL.GL_TRUE, value)
            GL.glUniform2f(GL.glGetUniformLocation(p, 'scaledViewSize'), width, height)
            GL.glUniform2f(GL.glGetUniformLocation(p, 'scaledTexelSize'), 1 / width, 1 / height)
            GL.glUniform3f(GL.glGetUniformLocation(p, 'cameraPosition'), *camera)
        set_lights(lights)
        GL.glBindImageTexture(0, low, 0, False, 0, GL.GL_WRITE_ONLY, GL.GL_RGBA32UI)
        GL.glBindImageTexture(1, high, 0, False, 0, GL.GL_WRITE_ONLY, GL.GL_RGBA32UI)
        GL.glUseProgram(selector)
        GL.glDispatchCompute((tw + 7) // 8, (th + 7) // 8, 1)
        GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, int(buffers[1]))
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER, width * height * 16, None, GL.GL_DYNAMIC_READ)
        state.update(width=width, height=height, tw=tw, th=th, low=low, high=high, lights=lights)

    def read_mask(tex, tw, th):
        GL.glActiveTexture(GL.GL_TEXTURE0 + 6); GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        raw = GL.glGetTexImage(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA_INTEGER, GL.GL_UNSIGNED_INT)
        return np.asarray(raw, np.uint32).reshape(th, tw, 4)

    def mask_bits(tile_x, tile_y):
        bits = set()
        for half, tex in ((0, state['low']), (1, state['high'])):
            words = read_mask(tex, state['tw'], state['th'])[tile_y, tile_x]
            for w, word in enumerate(words):
                for b in range(32):
                    if int(word) >> b & 1:
                        bits.add(half * 128 + w * 32 + b)
        return bits

    def run(width, height, mode=0, samples=1, only=0):
        GL.glUseProgram(shader)
        GL.glUniform1i(GL.glGetUniformLocation(shader, 'mode'), mode)
        GL.glUniform1i(GL.glGetUniformLocation(shader, 'testSamples'), samples)
        GL.glUniform1i(GL.glGetUniformLocation(shader, 'only'), only)
        GL.glDispatchCompute((width + 7) // 8, (height + 7) // 8, 1)
        GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER, int(buffers[1]))
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER, 0, width * height * 16),
                             np.float32).reshape(height, width, 4)[:, :, :3].copy()

    def tile_step(field):
        """Discontinuity that exists *only* on the 16 px tile grid.

        For every tile border column the jump across the border is compared with
        the jumps immediately beside it in the same row. A continuous field has
        no excess there; a per-tile light set or a per-tile gate leaves a step.
        """
        lum = field.sum(axis=2)
        jump = np.abs(np.diff(lum, axis=1))
        width = jump.shape[1]
        excess = 0.0
        for k in range(1, state['width'] // TILE):
            x = k * TILE - 1
            if x >= width:
                continue
            left = jump[:, x - 1] if x > 0 else np.zeros(jump.shape[0])
            right = jump[:, x + 1] if x + 1 < width else left
            excess = max(excess, float(np.max(jump[:, x] - np.maximum(left, right))))
        interior = jump[:, [(x % TILE) != (TILE - 1) for x in range(width)]]
        scale = float(np.percentile(interior, 99)) if interior.size else 0.0
        return excess, excess / max(scale, 1e-7)

    rng = np.random.default_rng(2718)
    scenes = []
    # A ceiling strip like the reported room: one row of lamps along x.
    scenes.append(('ceiling strip, 12 lamps', np.column_stack((
        np.linspace(-7, 7, 12), np.full(12, 2.5), np.full(12, -1.5), np.full(12, 11))).astype(np.float32)))
    # Two staggered rows: every tile sees a different nearest four.
    scenes.append(('staggered 12 lamps', np.column_stack((
        np.tile(np.linspace(-6, 6, 6), 2), np.repeat([3.0, 1.0], 6),
        np.repeat([-1.0, -2.5], 6), np.full(12, 11))).astype(np.float32)))
    scenes.append(('random 10 lamps', np.column_stack((
        rng.uniform(-7, 7, 10), rng.uniform(-4, 4, 10), rng.uniform(-2.5, 0.5, 10),
        np.full(10, 11))).astype(np.float32)))

    per_scene = []
    for name, lights in scenes:
        w, h = 192, 144
        setup(w, h, lights)
        current = run(w, h, 0)
        exhaustive = run(w, h, 1)
        shipped = run(w, h, 2)
        error = float(np.max(np.abs(current - exhaustive)))
        cur_excess, cur_ratio = tile_step(current)
        old_excess, old_ratio = tile_step(shipped)
        check(f'{name}: mask integration equals exhaustive integration', error < 2e-4, max_error=error)
        check(f'{name}: no discontinuity on the 16 px tile grid', cur_excess < 1e-3,
              tile_excess=round(cur_excess, 6), ratio_to_local_variation=round(cur_ratio, 3))
        check(f'{name}: shipped v7.1 selector still chains 16 px blocks at lamp junctions',
              old_excess > 0.005 and old_excess > 20 * max(cur_excess, 1e-7),
              tile_excess=round(old_excess, 6), ratio_to_local_variation=round(old_ratio, 3))
        # Conservativity: the mask must contain every light that reaches any pixel of the tile.
        missing = []
        for index in range(len(lights)):
            per_light = np.abs(run(w, h, 4, 1, index)).sum(axis=2)
            for ty in range(state['th']):
                for tx in range(state['tw']):
                    block = per_light[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE]
                    if block.size and block.max() > 1e-6 and index not in mask_bits(tx, ty):
                        missing.append((int(index), int(tx), int(ty), float(block.max())))
        check(f'{name}: tile masks contain every contributing light', not missing,
              missing=missing[:6], missing_count=len(missing), lights=len(lights))
        per_scene.append(dict(scene=name, max_error=error, tile_step_excess=round(cur_excess, 6),
                              shipped_tile_step_excess=round(old_excess, 6),
                              shipped_ratio_to_local=round(old_ratio, 3), minecraft_fps_measured=False))
        if name.startswith('staggered'):
            panels = []
            for rgb, label in ((shipped, 'v7.1: nearest 4 lights per 16 px tile'),
                               (current, 'current: every intersecting light')):
                display = np.power(np.clip(rgb / (1 + rgb), 0, 1), 1 / 2.2)
                panels.append((Image.fromarray(np.uint8(display * 255)), label))
            diff = np.abs(shipped - current).sum(axis=2)
            heat = diff / max(diff.max(), 1e-6)
            rgb_heat = np.stack([np.clip(heat * 1.6, 0, 1), np.clip(heat * 0.6, 0, 1), heat * 0.15], axis=2)
            panels.append((Image.fromarray(np.uint8(np.clip(rgb_heat, 0, 1) * 255)),
                           'v7.1 difference, amplified (bright = dropped light per tile)'))
            scale = 516 / panels[0][0].width
            size = (516, int(panels[0][0].height * scale))
            canvas = Image.new('RGB', (516 * 3, size[1] + 44), (18, 18, 18))
            draw = ImageDraw.Draw(canvas)
            for i, (panel, label) in enumerate(panels):
                canvas.paste(panel.resize(size), (i * 516, 30))
                draw.text((8 + i * 516, 10), label, fill='white')
            draw.text((8, size[1] + 32), 'GPU lab figure: same lights, same receiver - not a Minecraft screenshot',
                      fill=(200, 200, 200))
            canvas.save(ROOT / 'validation' / args.preview_name)

    # Local volumetric in-scattering must not switch off on a tile border either.
    lights = np.array([[-5, 2, -1, 11], [5, 2, -1, 11], [0, 3, -1.5, 11],
                       [6.5, 4.5, -0.5, 3], [-6.5, 4.5, -0.5, 3]], np.float32)
    setup(96, 64, lights)
    fog = run(96, 64, 3)
    fog_excess, fog_ratio = tile_step(fog)
    check('local volumetric in-scattering is continuous across tile borders', fog_excess < 1e-3,
          tile_excess=round(fog_excess, 6), ratio_to_local_variation=round(fog_ratio, 3))

    assert source_digest() == digest, 'Sources changed during seam tests'
    report = {'source_digest': digest, 'renderer': GL.glGetString(GL.GL_RENDERER).decode(),
              'passed': all(t['passed'] for t in tests), 'runtime_game_validation': False,
              'scenes': per_scene, 'tests': tests}
    (ROOT / 'validation' / args.report_name).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    glfw.destroy_window(window); glfw.terminate()
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
