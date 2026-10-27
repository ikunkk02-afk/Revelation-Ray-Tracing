"""Compile real shader entry points on a hidden OpenGL compatibility context.

Requires glfw and PyOpenGL. Does not emulate Iris's shader patcher, allocate the
game render graph, or establish in-game visual quality/performance.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import glfw
from OpenGL import GL

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "shaders"
BASE_MACROS = """
#define IS_IRIS
#define MC_VERSION 12101
#define MC_SHADOW_QUALITY 1.0
#define MC_RENDER_QUALITY 1.0
#define MC_HAND_DEPTH 0.125
#define MC_OS_WINDOWS
#define MC_GL_VENDOR_NVIDIA
#define MC_NORMAL_MAP
#define MC_SPECULAR_MAP
#define FORCE_DISABLE_SUBGROUP_OPS
"""


def expand(path: Path, stack: tuple[Path, ...] = ()) -> str:
    if path in stack:
        raise ValueError(f"Cyclic include: {path}")
    text = path.read_text(encoding="utf-8")
    return re.sub(r'^\s*#include\s+"([^"]+)"\s*$',
                  lambda m: expand((SHADERS / m[1].lstrip("/")) if m[1].startswith("/") else (path.parent / m[1]).resolve(), stack + (path,)),
                  text, flags=re.M)


def apply_options(text: str, options: dict[str, str | bool]) -> str:
    for name, value in options.items():
        pattern = rf'(?m)^([ \t]*)(?://[ \t]*)?#define[ \t]+{re.escape(name)}(?:[ \t]+[^\n]*)?$'
        replacement = f"#define {name}" if value is True else f"// #define {name}" if value is False else f"#define {name} {value}"
        text = re.sub(pattern, lambda _: replacement, text)
        if not isinstance(value, bool):
            # Iris also exposes const int/float options (e.g. shadow resolution).
            text = re.sub(rf'(const\s+(?:int|float)\s+{re.escape(name)}\s*=\s*)[^;]+;',
                          lambda m: m[1] + value + ';', text)
    return text


def source(path: Path, options: dict[str, str | bool]) -> str:
    text = apply_options(expand(path), options)
    first, rest = text.split("\n", 1)
    return first + "\n" + BASE_MACROS + rest


def profile_options(name: str) -> dict[str, str | bool]:
    properties = (SHADERS / "shaders.properties").read_text(encoding="utf-8")
    profiles = dict(re.findall(r'^profile\.([^ ]+)\s*=\s*(.*)$', properties, re.M))
    result = {}
    for token in profiles[name].split():
        if token.startswith("profile."):
            result.update(profile_options(token[8:]))
        elif ":" in token:
            key, value = token.split(":", 1)
            result[key] = value
        elif token.startswith("!"):
            result[token[1:]] = False
        elif token != "*":
            result[token] = True
    return result


def compile_shader(path: Path, options: dict[str, str | bool]) -> tuple[bool, str]:
    stage = {".csh": GL.GL_COMPUTE_SHADER, ".fsh": GL.GL_FRAGMENT_SHADER, ".vsh": GL.GL_VERTEX_SHADER}[path.suffix]
    shader = GL.glCreateShader(stage)
    try:
        GL.glShaderSource(shader, source(path, options))
        GL.glCompileShader(shader)
        ok = bool(GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS))
        log = GL.glGetShaderInfoLog(shader)
        if isinstance(log, bytes): log = log.decode("utf-8", "replace")
        return ok, log
    finally:
        GL.glDeleteShader(shader)


def ray_tests() -> list[dict]:
    """Execute the production ray marcher against controlled GPU depth buffers."""
    import numpy as np
    text = "#version 460 compatibility\n" + BASE_MACROS
    for name in ("lib/Utility.glsl", "lib/universal/Uniform.glsl", "lib/universal/Transform.glsl", "lib/lighting/SSRT.glsl"):
        text += expand(SHADERS / name) + "\n"
    text = re.sub(r'(?m)^\s*#define TAA_ENABLED.*$', '// TAA disabled in deterministic test', text)
    text += """
layout(local_size_x=1) in;
layout(std430,binding=7) buffer RayResults { vec4 results[]; };
uniform vec4 testOrigin[9];
uniform vec3 testDirection[9];
void main() {
    uint i=gl_GlobalInvocationID.x;
    vec3 hit;
    bool found=TraceScreenRay(testOrigin[i].xyz,testDirection[i],0.5,96u,testOrigin[i].w,hit);
    results[i]=vec4(found ? 1.0 : 0.0, found ? ScreenToViewPos(hit) : vec3(0.0));
}
"""
    shader = GL.glCreateShader(GL.GL_COMPUTE_SHADER)
    GL.glShaderSource(shader, text)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        raise RuntimeError(GL.glGetShaderInfoLog(shader))
    program = GL.glCreateProgram()
    GL.glAttachShader(program, shader)
    GL.glLinkProgram(program)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(program))
    GL.glUseProgram(program)
    near, far = 0.05, 128.0
    projection = np.array([[1,0,0,0],[0,1,0,0],[0,0,-(far+near)/(far-near),-2*far*near/(far-near)],[0,0,-1,0]], dtype=np.float32)
    GL.glUniformMatrix4fv(GL.glGetUniformLocation(program,"gbufferProjection"),1,GL.GL_TRUE,projection)
    GL.glUniformMatrix4fv(GL.glGetUniformLocation(program,"gbufferProjectionInverse"),1,GL.GL_TRUE,np.linalg.inv(projection))
    GL.glUniform1f(GL.glGetUniformLocation(program,"near"),near)
    GL.glUniform2f(GL.glGetUniformLocation(program,"scaledViewSize"),64,64)
    origins=np.array([[0,0,-2,10],[0,0,-2,1],[0,0,-2,10],[0,0,-2,10],[0,0,-5,10],[0,0,-2,0],[0,0,-2,10],[0,0,0,10],[0,0,-2,10]],dtype=np.float32)
    directions=np.array([[0,0,-1],[0,0,-1],[0,1,0],[1,0,-1],[0,0,1],[0,0,-1],[0,0,0],[0,0,-1],[10,0,-1]],dtype=np.float32)
    GL.glUniform4fv(GL.glGetUniformLocation(program,"testOrigin"),9,origins)
    GL.glUniform3fv(GL.glGetUniformLocation(program,"testDirection"),9,directions)
    GL.glUniform1i(GL.glGetUniformLocation(program,"depthtex2"),0)
    texture=GL.glGenTextures(1)
    GL.glActiveTexture(GL.GL_TEXTURE0)
    GL.glBindTexture(GL.GL_TEXTURE_2D,texture)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    buffer=GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffer)
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,9*16,None,GL.GL_DYNAMIC_READ)
    GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,7,buffer)
    tests=[]
    planeDepth = (far/(far-near)) - (far*near/(far-near))/4.0
    for scene, depth, expected in (("plane",planeDepth,[True,False,False,True,True,False,False,False,False]),("sky",1.0,[False]*9)):
        pixels=np.full((64,64),depth,dtype=np.float32)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D,texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_R32F,64,64,0,GL.GL_RED,GL.GL_FLOAT,pixels)
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,9*16,None,GL.GL_DYNAMIC_READ)
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,7,buffer)
        GL.glDispatchCompute(9,1,1)
        GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        result=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,9*16),dtype=np.float32).reshape(9,4)
        for i, wanted in enumerate(expected):
            found=bool(result[i,0]>0.5)
            ok=found==wanted and bool(np.isfinite(result[i]).all())
            if found: ok=ok and abs(float(result[i,3])+4.0)<0.02
            tests.append({"scene":scene,"ray":i,"expected_hit":wanted,"result":result[i].tolist(),"passed":ok})
    GL.glDeleteBuffers(1,[buffer])
    GL.glDeleteTextures([texture])
    GL.glDeleteProgram(program)
    GL.glDeleteShader(shader)
    return tests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not glfw.init(): raise RuntimeError("GLFW initialization failed")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 6)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_COMPAT_PROFILE)
    window = glfw.create_window(32, 32, "Revelation RT validation", None, None)
    if not window: raise RuntimeError("OpenGL 4.6 compatibility context unavailable")
    glfw.make_context_current(window)
    report = {"renderer": GL.glGetString(GL.GL_RENDERER).decode(),
              "version": GL.glGetString(GL.GL_VERSION).decode(), "checks": []}
    report["ray_tests"] = ray_tests()
    from validate_rt_glass import run_glass_tests
    from validate_rt_shadow import run_shadow_tests
    report["transmission_tests"] = run_glass_tests()
    report["shadow_tests"] = run_shadow_tests()
    for group in ("transmission_tests", "shadow_tests"):
        if not all(t["passed"] for t in report[group]):
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report[group], indent=2))
            raise SystemExit(f"{group} failed")
    if not all(t["passed"] for t in report["ray_tests"]):
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report["ray_tests"], indent=2))
        raise SystemExit("GPU ray tests failed")
    variants = {
        **{name: profile_options(name) for name in ("RT_5060", "RT_Ultra", "RT_Cinematic", "Legacy_GI")},
        "RT_no_SVGF": {"SVGF_ENABLED": False},
        "RT_PBR": {"RP_SUPPORT": True},
        "RT_colored_hand": {"COLORED_HANDHELD_LIGHTING": True},
        "RT_scaled": {"RENDER_SCALE_1000X": "667"},
        "RT_DH": {},
        "RT_glass_off": {"RT_GLASS_ENABLED": False},
        "RT_soft_shadow": {"RT_HANDHELD_RADIUS": "0.02", "RT_HANDHELD_SOFT_SAMPLES": "4"},
    }
    names = ["begin.csh", "shadow.vsh", "shadow.fsh", "deferred1.csh", "deferred1_a.csh", "deferred4.fsh", "deferred21.fsh", "deferred50.fsh", "composite1.fsh", "composite1.csh", "composite2.csh", "composite2.fsh", "final.fsh"]
    # Check the complete include graph, including optional integrations.
    entries = [p for p in SHADERS.rglob("*") if p.suffix in (".csh", ".fsh", ".vsh")]
    for p in entries: expand(p)
    report["include_graph_entrypoints"] = len(entries)
    # Locate the translucent compute pass from its include instead of assuming its number.
    translucent = [p.name for p in (SHADERS / "world0").glob("*.csh")
                   if '"/program/Translucent.comp"' in p.read_text(encoding="utf-8")]
    names = list(dict.fromkeys(names + translucent))
    for variant, options in variants.items():
        for dimension in ("world0", "world-1"):
            for name in names:
                p = SHADERS / dimension / name
                if not p.exists(): continue
                extra = dict(options)
                text = source(p, extra)
                if variant == "RT_DH":
                    text = text.replace(BASE_MACROS, BASE_MACROS + "#define DISTANT_HORIZONS\n")
                stage = {".csh":GL.GL_COMPUTE_SHADER,".fsh":GL.GL_FRAGMENT_SHADER,".vsh":GL.GL_VERTEX_SHADER}[p.suffix]
                shader = GL.glCreateShader(stage)
                GL.glShaderSource(shader, text)
                GL.glCompileShader(shader)
                ok = bool(GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS))
                log = GL.glGetShaderInfoLog(shader)
                if isinstance(log, bytes): log = log.decode("utf-8", "replace")
                if ok:
                    program = GL.glCreateProgram()
                    if p.suffix != ".vsh":
                        GL.glProgramParameteri(program, GL.GL_PROGRAM_SEPARABLE, GL.GL_TRUE)
                    GL.glAttachShader(program, shader)
                    pair = None
                    if p.suffix == ".vsh":
                        pair = GL.glCreateShader(GL.GL_FRAGMENT_SHADER)
                        GL.glShaderSource(pair, source(p.with_suffix(".fsh"), extra))
                        GL.glCompileShader(pair)
                        GL.glAttachShader(program, pair)
                    GL.glLinkProgram(program)
                    ok = bool(GL.glGetProgramiv(program, GL.GL_LINK_STATUS))
                    linklog = GL.glGetProgramInfoLog(program)
                    if isinstance(linklog, bytes): linklog = linklog.decode("utf-8", "replace")
                    log += linklog
                    GL.glDeleteProgram(program)
                    if pair is not None: GL.glDeleteShader(pair)
                GL.glDeleteShader(shader)
                report["checks"].append({"variant": variant, "file": str(p.relative_to(ROOT)), "passed": ok, "log": log})
                if not ok:
                    dump = args.report.parent / "failed_shader.glsl"
                    dump.write_text(text, encoding="utf-8")
                    print(variant, dimension, name, log, flush=True)
                    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
                    raise SystemExit(1)
        print(f"Compiled {variant}", flush=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    glfw.destroy_window(window)
    glfw.terminate()
    behavior_count=sum(len(report[k]) for k in ("ray_tests","transmission_tests","shadow_tests"))
    print(f"PASS: {len(report['checks'])} shader compile/link checks, {behavior_count} GPU behavior tests on {report['renderer']}")


if __name__ == "__main__": main()
