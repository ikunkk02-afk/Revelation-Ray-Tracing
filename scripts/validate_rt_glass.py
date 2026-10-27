"""GPU behavior tests for the production glass grid, pane bounds and transmission.
Run with validate_rt.py's hidden OpenGL context current.
"""
from __future__ import annotations

import math
import numpy as np
from OpenGL import GL
from validate_rt import BASE_MACROS, SHADERS, expand


def program(text: str) -> int:
    shader = GL.glCreateShader(GL.GL_COMPUTE_SHADER)
    GL.glShaderSource(shader, text)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        raise RuntimeError(GL.glGetShaderInfoLog(shader))
    result = GL.glCreateProgram()
    GL.glAttachShader(result, shader)
    GL.glLinkProgram(result)
    GL.glDeleteShader(shader)
    if not GL.glGetProgramiv(result, GL.GL_LINK_STATUS):
        raise RuntimeError(GL.glGetProgramInfoLog(result))
    return result


def run_glass_tests() -> list[dict]:
    header = "#version 460 compatibility\n" + BASE_MACROS
    header += expand(SHADERS / "lib/Utility.glsl") + "\n"
    header += expand(SHADERS / "lib/universal/Uniform.glsl") + "\n"
    reader = program(header + expand(SHADERS / "lib/lighting/GlassGrid.glsl") + """
layout(local_size_x=1) in;
layout(std430,binding=7) buffer TestOutput { vec4 result; };
uniform vec3 rayOrigin;
uniform vec3 rayTarget;
void main() { result=vec4(RTTraceGlass(rayOrigin,rayTarget),1.0); }
""")
    writer = program(header + "\n#define RT_GLASS_WRITE\n" + expand(SHADERS / "lib/lighting/GlassGrid.glsl") + """
layout(local_size_x=1) in;
uniform int testBlockID;
uniform vec3 testCenter;
void main() { RTRecordGlass(testBlockID,testCenter); }
""")
    clearer = program("#version 460 compatibility\n" + BASE_MACROS + expand(SHADERS / "program/prepare/ClearGlassGrid.comp"))
    texture = GL.glGenTextures(1)
    GL.glActiveTexture(GL.GL_TEXTURE0)
    GL.glBindTexture(GL.GL_TEXTURE_3D, texture)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    pixels = np.zeros((64,64,64), dtype=np.uint32)
    GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_R32UI,64,64,64,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,pixels)
    state, output = [int(v) for v in GL.glGenBuffers(2)]
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,state)
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,16,np.zeros(4,dtype=np.uint32),GL.GL_DYNAMIC_COPY)
    GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,4,state)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,output)
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,16,None,GL.GL_DYNAMIC_READ)
    GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,7,output)
    GL.glUseProgram(reader)
    GL.glUniform1i(GL.glGetUniformLocation(reader,"rtGlassGridTex"),0)
    GL.glUniformMatrix4fv(GL.glGetUniformLocation(reader,"gbufferModelViewInverse"),1,GL.GL_FALSE,np.eye(4,dtype=np.float32))
    tests = []

    def trace(name, cells, origin=(0.5,0.5,-2), target=(0.5,0.5,2), expected=None, camera=(0,0,0), occupied=1):
        pixels.fill(0)
        for x,y,z,code in cells: pixels[z+32,y+32,x+32]=code
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_3D,texture)
        GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,pixels)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,state)
        GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16,np.array([occupied,0,0,0],dtype=np.uint32))
        GL.glUseProgram(reader)
        GL.glUniform3f(GL.glGetUniformLocation(reader,"rayOrigin"),*origin)
        GL.glUniform3f(GL.glGetUniformLocation(reader,"rayTarget"),*target)
        GL.glUniform3f(GL.glGetUniformLocation(reader,"cameraPosition"),*camera)
        GL.glDispatchCompute(1,1,1)
        GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,output)
        result = np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16),dtype=np.float32)[:3].copy()
        ok = bool(np.isfinite(result).all() and (result>=0).all() and (result<=1).all())
        if expected is not None: ok = ok and bool(np.allclose(result,expected,atol=3e-4,rtol=2e-3))
        tests.append({"name":name,"result":result.tolist(),"passed":ok})
        return result

    red_code, blue_code = 15, 12
    red = trace("red_full_cube",[(0,0,0,red_code)])
    tests[-1]["passed"] &= bool(red[0]>red[1]*1.5 and red[0]>red[2]*1.5)
    blue = trace("blue_full_cube",[(0,0,0,blue_code)])
    tests[-1]["passed"] &= bool(blue[2]>blue[0]*1.5)
    trace("empty_grid",[],expected=np.ones(3),occupied=0)
    trace("miss_cube",[(0,0,0,red_code)],origin=(1.5,0.5,-2),target=(1.5,0.5,2),expected=np.ones(3))
    trace("finite_light_before_glass",[(0,0,0,red_code)],target=(0.5,0.5,-0.1),expected=np.ones(3))
    trace("two_red_layers",[(0,0,0,red_code),(0,0,1,red_code)],target=(0.5,0.5,3),expected=red*red)
    trace("red_blue_layers",[(0,0,0,red_code),(0,0,1,blue_code)],target=(0.5,0.5,3),expected=red*blue)
    trace("reverse_ray",[(0,0,0,red_code)],origin=(0.5,0.5,2),target=(0.5,0.5,-2),expected=red)
    trace("diagonal_tied_dda_axes",[(0,0,0,red_code)],origin=(-1,-1,-1),target=(2,2,2),expected=red**math.sqrt(3))
    trace("source_inside_glass",[(0,0,0,red_code)],origin=(0.5,0.5,0.5),expected=np.sqrt(red))
    trace("clear_glass",[(0,0,0,17)],expected=np.full(3,0.985))
    trace("zero_length",[(0,0,0,red_code)],origin=(0.5,0.5,0.5),target=(0.5,0.5,0.5),expected=np.ones(3))
    trace("outside_grid",[(0,0,0,red_code)],origin=(100,0,-2),target=(100,0,2),expected=np.ones(3))
    trace("negative_camera_fraction",[(0,0,0,red_code)],origin=(-0.4,-0.3,-2.7),target=(-0.4,-0.3,1.3),camera=(0.9,-0.2,0.7),expected=red)
    trace("cleared_frame_flag",[(0,0,0,red_code)],occupied=0,expected=np.ones(3))
    pane_ns = red_code | 32 | (5<<6)
    trace("thin_pane_normal_incidence",[(0,0,0,pane_ns)],origin=(-2,0.5,0.25),target=(2,0.5,0.25),expected=red**0.125)
    trace("pane_edge_on_length",[(0,0,0,pane_ns)],expected=red)
    trace("isolated_pane_empty_corner",[(0,0,0,red_code|32)],origin=(-2,0.5,0.25),target=(2,0.5,0.25),expected=np.ones(3))
    trace("unconnected_pane_arm",[(0,0,0,red_code|32|(1<<6))],origin=(-2,0.5,0.75),target=(2,0.5,0.75),expected=np.ones(3))
    trace("connected_pane_arm",[(0,0,0,red_code|32|(1<<6))],origin=(-2,0.5,0.25),target=(2,0.5,0.25),expected=red**0.125)
    trace("pane_union_no_double_absorption",[(0,0,0,red_code|32|(15<<6))],origin=(-2,0.5,0.5),target=(2,0.5,0.5),expected=red)

    GL.glBindImageTexture(0,texture,0,GL.GL_TRUE,0,GL.GL_READ_WRITE,GL.GL_R32UI)
    GL.glUseProgram(clearer)
    GL.glUniform1i(GL.glGetUniformLocation(clearer,"rtGlassGrid"),0)
    GL.glDispatchCompute(8,8,8)
    GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    GL.glBindTexture(GL.GL_TEXTURE_3D,texture)
    cleared = np.frombuffer(GL.glGetTexImage(GL.GL_TEXTURE_3D,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT),dtype=np.uint32)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,state)
    flag = np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4),dtype=np.uint32)[0]
    tests.append({"name":"production_frame_clear","passed":bool(not cleared.any() and flag==0)})

    GL.glUseProgram(writer)
    GL.glUniform1i(GL.glGetUniformLocation(writer,"rtGlassGrid"),0)
    GL.glUniform3f(GL.glGetUniformLocation(writer,"cameraPosition"),0.9,-0.2,0.7)
    GL.glUniform3f(GL.glGetUniformLocation(writer,"testCenter"),-0.4,-0.3,-0.2)
    GL.glUniform1i(GL.glGetUniformLocation(writer,"testBlockID"),13015)
    GL.glDispatchCompute(1,1,1)
    GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    captured = np.frombuffer(GL.glGetTexImage(GL.GL_TEXTURE_3D,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT),dtype=np.uint32).reshape(64,64,64)
    flag = np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4),dtype=np.uint32)[0]
    tests.append({"name":"capture_world_cell_negative_camera","passed":bool(captured[32,32,32]==red_code and np.count_nonzero(captured)==1 and flag==1)})
    GL.glUniform1i(GL.glGetUniformLocation(writer,"testBlockID"),14229) # red pane, north + south
    GL.glDispatchCompute(1,1,1)
    GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    captured = np.frombuffer(GL.glGetTexImage(GL.GL_TEXTURE_3D,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT),dtype=np.uint32).reshape(64,64,64)
    tests.append({"name":"capture_connected_pane_encoding","passed":bool(captured[32,32,32]==pane_ns)})
    for p in (reader,writer,clearer): GL.glDeleteProgram(p)
    GL.glDeleteBuffers(2,[state,output])
    GL.glDeleteTextures([texture])
    return tests
