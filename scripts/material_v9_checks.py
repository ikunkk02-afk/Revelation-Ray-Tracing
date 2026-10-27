"""Run material decoding on the GPU; independent LabPBR byte-range expectations."""
import json
import glfw
import numpy as np
from OpenGL import GL
from validate_rt import SHADERS, BASE_MACROS, expand, apply_options
from validate_rt_glass import program
from rt_source_digest import source_digest

def main():
    digest=source_digest()
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,6)
    glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_COMPAT_PROFILE)
    window=glfw.create_window(16,16,'Material decoding',None,None)
    assert window
    glfw.make_context_current(window)
    header='#version 460 compatibility\n'+BASE_MACROS
    for name in ('lib/Utility.glsl','lib/surface/Material.glsl'):
        header+=expand(SHADERS/name)+'\n'
    body='''
layout(local_size_x=64) in;
layout(std430,binding=7) buffer Output {vec4 result[];};
void main(){uint i=gl_GlobalInvocationID.x;if(i>=256u)return;
 vec2 tex=vec2(.1,float(i)/255.0);
 Material a=GetMaterialData(vec4(tex,0,0),vec3(.5));
 Material b=GetMaterialData(tex,vec3(.5));Material c=GetMaterialData(tex);
 result[i*3u]=vec4(a.reflectance,a.metallic);
 result[i*3u+1u]=vec4(b.reflectance,b.metallic);
 result[i*3u+2u]=vec4(a.roughness,float(a.specularMask),c.metallic,float(c.specularMask));}
'''
    buffer=int(GL.glGenBuffers(1));GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,7,buffer)
    GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,256*3*16,None,GL.GL_DYNAMIC_READ)
    tests=[]
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details))
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    for fmt in (0,1):
        p=program(apply_options(header+body,{'TEXTURE_FORMAT':str(fmt),'LABPBR_HARDCODED_METAL':False}))
        GL.glUseProgram(p);GL.glDispatchCompute(4,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        v=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,256*3*16),np.float32).reshape(256,3,4)
        check(f'Format {fmt}: finite outputs across all 256 channel values',np.isfinite(v).all())
        check(f'Format {fmt}: both full material overloads agree',np.allclose(v[:,0],v[:,1],atol=1e-6))
        if fmt==0:
            check('LabPBR 1..229 encode F0 directly',np.allclose(v[1:230,0,:3],np.arange(1,230)[:,None]/255,atol=1e-6))
            check('LabPBR 0..229 are dielectrics in every overload',np.all(v[:230,0,3]==0) and np.all(v[:230,2,2]==0))
            check('LabPBR 230..255 are fully metallic',np.all(v[230:,0,3]==1) and np.all(v[230:,2,2]==1))
            check('Rough dielectrics avoid unnecessary SSR; metals retain SSR',np.all(v[:230,2,1]==0) and np.all(v[230:,2,1]==1))
            check('Missing map retains default dielectric F0',np.allclose(v[0,0,:3],.04))
            check('F0 10/255 is not remapped to 7.76 percent',abs(float(v[10,0,0])-10/255)<1e-6,
                  old_F0=.04+.96*10/255,new_F0=float(v[10,0,0]))
        else:
            check('OldPBR continuous metalness preserved',np.allclose(v[:,0,3],np.arange(256)/255,atol=1e-6))
        GL.glDeleteProgram(p)
    assert digest==source_digest()
    report=dict(source_digest=digest,renderer=GL.glGetString(GL.GL_RENDERER).decode(),passed=all(x['passed'] for x in tests),
                reference='https://shaderlabs.org/wiki/LabPBR_Material_Standard',tests=tests,runtime_game_validation=False)
    (SHADERS.parent/'validation/material-v9.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
