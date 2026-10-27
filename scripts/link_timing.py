"""Time glCompileShader + glLinkProgram for one shader entry point.

Used to find compute programs whose linkage makes the NVIDIA driver stall, which
is what freezes the client at "Creating pipeline for dimension ...".
"""
from pathlib import Path
import json
import sys
import time

import glfw
from OpenGL import GL

from validate_rt import SHADERS, source, profile_options
from validate_rt_glass import program

OVERRIDES = Path(r'D:\HMCL\.minecraft\versions\1.21.1-fabric\shaderpacks'
                 r'\Revelation-RT-v8.1-StartupFix.zip.txt')


def options():
    opts = profile_options(sys.argv[2] if len(sys.argv) > 2 and not '=' in sys.argv[2] else 'RayTracing')
    if OVERRIDES.exists():
        for line in OVERRIDES.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.startswith('#'):
                continue
            key, value = line.split('=', 1)
            opts[key] = True if value == 'true' else False if value == 'false' else value
    for extra in sys.argv[2:]:
        if '=' in extra:
            key, value = extra.split('=', 1)
            opts[key] = True if value == 'true' else False if value == 'false' else value
    return opts


def main():
    target = Path(sys.argv[1])
    if not target.is_absolute():
        target = SHADERS / target
    opts = options()
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 6)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(16, 16, 'link timing', None, None)
    assert window
    glfw.make_context_current(window)
    text = source(target, opts)
    stage = {'.csh': GL.GL_COMPUTE_SHADER, '.fsh': GL.GL_FRAGMENT_SHADER, '.vsh': GL.GL_VERTEX_SHADER}[target.suffix]
    shader = GL.glCreateShader(stage)
    GL.glShaderSource(shader, text)
    start = time.perf_counter()
    GL.glCompileShader(shader)
    compile_s = time.perf_counter() - start
    compiled = bool(GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS))
    log = GL.glGetShaderInfoLog(shader).strip()
    prog = GL.glCreateProgram()
    GL.glAttachShader(prog, shader)
    start = time.perf_counter()
    print(f'LINK {target.name}', flush=True)
    GL.glLinkProgram(prog)
    link_s = time.perf_counter() - start
    linked = bool(GL.glGetProgramiv(prog, GL.GL_LINK_STATUS))
    print(json.dumps({'file': str(target.relative_to(SHADERS)), 'compile_s': round(compile_s, 3),
                      'link_s': round(link_s, 3), 'compiled': compiled, 'linked': linked,
                      'locals': len(text), 'log': log[:200]}), flush=True)
    glfw.terminate()


if __name__ == '__main__':
    main()
