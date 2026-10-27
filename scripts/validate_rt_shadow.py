"""Execute the production handheld-light shader against a sharp depth edge."""
from __future__ import annotations

import re
import numpy as np
from OpenGL import GL
from validate_rt import BASE_MACROS, SHADERS, expand
from validate_rt_glass import program


def run_shadow_tests() -> list[dict]:
    text = "#version 460 compatibility\n" + BASE_MACROS
    for name in ("lib/Utility.glsl", "lib/universal/Uniform.glsl", "lib/universal/Transform.glsl",
                 "lib/surface/Material.glsl", "lib/lighting/BRDF.glsl", "lib/lighting/HandheldTracing.glsl"):
        text += expand(SHADERS/name) + "\n"
    for name in ("TAA_ENABLED","RT_GLASS_ENABLED","RT_HANDHELD_FLICKER"):
        text = re.sub(rf'(?m)^\s*#define {name}.*$',f'// {name} disabled in controlled shadow test',text)
    text += """
layout(local_size_x=1) in;
layout(std430,binding=7) buffer ShadowTestOutput { vec4 results[]; };
void main() {
    uint i=gl_GlobalInvocationID.x;
    vec3 pos=vec3(mix(-1.0,1.0,float(i)/127.0),0.2,-3.0);
    Material material=Material(0.5,0.0,0.0,vec3(0.04),false,false);
    vec3 diffuse=vec3(0.0), specular=vec3(0.0);
    AddTracedHandheldLighting(pos,vec3(0.0,0.0,1.0),vec3(0.0,0.0,1.0),
        material,false,ivec2(i,64),diffuse,specular);
    results[i]=vec4(diffuse,1.0);
}
"""
    p=program(text)
    GL.glUseProgram(p)
    near,far=0.05,128.0
    projection=np.array([[1,0,0,0],[0,1,0,0],[0,0,-(far+near)/(far-near),-2*far*near/(far-near)],[0,0,-1,0]],dtype=np.float32)
    for name,matrix in (("gbufferProjection",projection),("gbufferProjectionInverse",np.linalg.inv(projection)),("gbufferModelView",np.eye(4,dtype=np.float32))):
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(p,name),1,GL.GL_TRUE,matrix)
    GL.glUniform1f(GL.glGetUniformLocation(p,"near"),near)
    GL.glUniform2f(GL.glGetUniformLocation(p,"scaledViewSize"),128,128)
    for name,value in (("depthtex2",0),("heldBlockLightValue",15),("heldBlockLightValue2",0),("heldItemId",10001),("isRightHanded",1)):
        GL.glUniform1i(GL.glGetUniformLocation(p,name),value)
    tex=GL.glGenTextures(1)
    GL.glActiveTexture(GL.GL_TEXTURE0)
    GL.glBindTexture(GL.GL_TEXTURE_2D,tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    buffer=GL.glGenBuffers(1)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffer)
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,128*16,None,GL.GL_DYNAMIC_READ)
    GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,7,buffer)

    def render(pixels,frame):
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D,tex)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_R32F,128,128,0,GL.GL_RED,GL.GL_FLOAT,pixels)
        GL.glUniform1i(GL.glGetUniformLocation(p,"frameCounter"),frame)
        GL.glDispatchCompute(128,1,1)
        GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffer)
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,128*16),dtype=np.float32).reshape(128,4)[:,:3].copy()

    sky=np.ones((128,128),dtype=np.float32)
    baseline=render(sky,0)
    depth=sky.copy()
    depth[:,:64]=far/(far-near)-(far*near/(far-near))/2.0
    first=render(depth,0)
    later=render(depth,17)
    third=render(depth,98)
    ratio=first[:,0]/np.maximum(baseline[:,0],1e-6)
    tests=[
        {"name":"handheld_light_unoccluded_positive","passed":bool(np.isfinite(baseline).all() and (baseline>0).all())},
        {"name":"handheld_depth_occlusion","passed":bool(np.max(first[:16])<1e-6 and np.all(first[-16:]>0))},
        {"name":"stationary_shadow_no_random_frame_variation","passed":bool(np.array_equal(first,later) and np.array_equal(first,third))},
        {"name":"default_edge_has_no_stochastic_gray_band","passed":bool(np.all((np.abs(ratio)<1e-5)|(np.abs(ratio-1)<1e-5))),
         "blocked_pixels":int(np.count_nonzero(ratio<0.5)),"lit_pixels":int(np.count_nonzero(ratio>=0.5))},
    ]
    GL.glDeleteProgram(p)
    GL.glDeleteBuffers(1,[buffer])
    GL.glDeleteTextures([tex])
    return tests
