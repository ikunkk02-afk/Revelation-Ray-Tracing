"""Execute production cutout, transmission, refraction and occlusion on the GPU.

Cutout expectations come from independent vanilla PNG columns and state rotations.
This is a controlled lighting lab, not Minecraft/Iris visual acceptance.
"""
from __future__ import annotations
import argparse, io, json, math, re, zipfile
from pathlib import Path
import glfw
import numpy as np
from PIL import Image
from OpenGL import GL
from validate_rt import BASE_MACROS, SHADERS, expand, apply_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT=SHADERS.parent
JAR=Path(r'D:\HMCL\.minecraft\versions\1.21.1-fabric\1.21.1-fabric.jar')

def shadow_alpha_tests():
    vertex='''#version 460 compatibility
out vec2 texCoord; out vec3 vectorData;
flat out uint isWater; flat out uint glassCode; out vec3 rtGlassLocalPos;
uniform uint testCode;
void main() {
    vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);
    gl_Position=vec4(p*2.0-1.0,0.0,1.0);
    texCoord=vec2(.5);vectorData=vec3(1.0);isWater=0u;glassCode=testCode;rtGlassLocalPos=vec3(.5);
}'''
    fragment='#version 460 compatibility\n'+BASE_MACROS+expand(SHADERS/'program/shadow/Shadow.frag')
    shaders=[]
    for stage,source_text in ((GL.GL_VERTEX_SHADER,vertex),(GL.GL_FRAGMENT_SHADER,fragment)):
        sh=GL.glCreateShader(stage);GL.glShaderSource(sh,source_text);GL.glCompileShader(sh)
        assert GL.glGetShaderiv(sh,GL.GL_COMPILE_STATUS),GL.glGetShaderInfoLog(sh)
        shaders.append(sh)
    p=GL.glCreateProgram()
    for sh in shaders:GL.glAttachShader(p,sh)
    GL.glLinkProgram(p);assert GL.glGetProgramiv(p,GL.GL_LINK_STATUS),GL.glGetProgramInfoLog(p)
    GL.glUseProgram(p);GL.glUniform3f(GL.glGetUniformLocation(p,'shadowDirWorld'),0,0,1)
    GL.glUniform1i(GL.glGetUniformLocation(p,'tex'),0)
    textures=GL.glGenTextures(3);fbo=GL.glGenFramebuffers(1);GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,fbo)
    for i,tex in enumerate(textures):
        GL.glActiveTexture(GL.GL_TEXTURE0+i);GL.glBindTexture(GL.GL_TEXTURE_2D,int(tex))
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA16F,1,1,0,GL.GL_RGBA,GL.GL_FLOAT,np.array([1,1,1,0],np.float32))
        if i:GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER,GL.GL_COLOR_ATTACHMENT0+i-1,GL.GL_TEXTURE_2D,int(tex),0)
    GL.glDrawBuffers([GL.GL_COLOR_ATTACHMENT0,GL.GL_COLOR_ATTACHMENT1])
    assert GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)==GL.GL_FRAMEBUFFER_COMPLETE
    GL.glViewport(0,0,1,1);GL.glDisable(GL.GL_DEPTH_TEST);GL.glDisable(GL.GL_BLEND)
    tests=[]
    for code in (17,0):
        GL.glClearBufferfv(GL.GL_COLOR,0,np.array([.125,.125,.125,1],np.float32))
        GL.glClearBufferfv(GL.GL_COLOR,1,np.zeros(4,np.float32))
        GL.glUniform1ui(GL.glGetUniformLocation(p,'testCode'),code);GL.glDrawArrays(GL.GL_TRIANGLES,0,3)
        GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
        rgb=np.frombuffer(GL.glReadPixels(0,0,1,1,GL.GL_RGBA,GL.GL_FLOAT),np.float32)[:3]
        GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT1)
        marker=np.frombuffer(GL.glReadPixels(0,0,1,1,GL.GL_RGBA,GL.GL_FLOAT),np.float32)[3]
        ok=np.allclose(rgb,np.full(3,.985**(1/3)),atol=.001) and abs(marker-.25)<.001 if code else np.allclose(rgb,.125)
        tests.append({'name':'Clear glass alpha-zero solar capture' if code else 'Opaque cutout alpha-zero remains discarded','passed':bool(ok),'result':rgb.tolist(),'marker':float(marker)})
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,0);GL.glDeleteFramebuffers(1,[fbo]);GL.glDeleteTextures(textures)
    GL.glDeleteProgram(p)
    for sh in shaders:GL.glDeleteShader(sh)
    return tests


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report-name',default='physical-probes-v8-regression.json')
    args=parser.parse_args()
    digest_before=source_digest()
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,6)
    glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_COMPAT_PROFILE)
    window=glfw.create_window(32,32,'RT v7 physical probes',None,None)
    assert window
    glfw.make_context_current(window)
    header='#version 460 compatibility\n'+BASE_MACROS
    for p in ('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/Transform.glsl',
              'lib/surface/Material.glsl','lib/lighting/BRDF.glsl',
              'lib/lighting/SceneGrid.glsl','lib/lighting/GlassOptics.glsl','lib/lighting/GlassGrid.glsl','lib/lighting/Emitters.glsl','lib/lighting/HandheldTracing.glsl','lib/lighting/LocalVolumetrics.glsl'):
        header+=expand(SHADERS/p)+'\n'
    baseline=expand(ROOT/'scripts/data/handheld-tracing-v7.glsl')
    baseline=baseline.replace('INCLUDE_LIB_LIGHTING_HANDHELD_TRACING','INCLUDE_LIB_LIGHTING_HANDHELD_TRACING_OLD').replace('AddTracedHandheldLighting','AddOldHandheldLighting').replace('RTHeldColor','OldHeldColor').replace('uniform bool isRightHanded;','')
    header+=baseline+'\n'
    # Exercise real occlusion/transmission in the optional local volume as well
    # as the production surface tracer; the shipped profile disables this fog.
    header=apply_options(header,{'RT_LOCAL_VOLUMETRICS':True,'RT_LOCAL_TRACED_SHADOWS':True})
    shader=program(header+'''
layout(local_size_x=64) in;
layout(std430,binding=8) readonly buffer Inputs { vec4 inputData[]; };
layout(std430,binding=7) writeonly buffer Outputs { vec4 outputData[]; };
uniform int mode;
uniform uint queryCount;
void main() {
    uint i=gl_GlobalInvocationID.x;
    if(i>=queryCount) return;
    vec4 a=inputData[2u*i], b=inputData[2u*i+1u];
    vec4 out0=vec4(0.0), out1=vec4(0.0);
    if (mode==0) out0.x=RTShapeHit(0x80000000u|uint(a.w+0.5),a.xyz,b.xyz,b.w)?1.0:0.0;
    if (mode==1) { float f=RTDielectricFresnel(a.x,a.y); out0=vec4(f,1.0-f,0,0); }
    if (mode==2) out0=vec4(RTGlassAbsorption(uint(a.w+.5),a.x),a.x);
    if (mode==3) {
        vec3 p,d; float length,transmission;
        bool valid=RTRefractGlass(a.xyz,b.xyz,uint(a.w+.5),p,d,length,transmission);
        out0=vec4(d,length); out1=vec4(p,valid?transmission:-1.0);
    }
    if (mode==4) out0.x=RTFalloff(a.x,a.y,a.z);
    if (mode==5) out0=vec4(RTTraceGlass(a.xyz,b.xyz),1.0);
    if (mode==6) out0.x=RTSceneOccluded(a.xyz,b.xyz)?1.0:0.0;
    if (mode==7 || mode==12) {
        Material material=Material(0.5,0.0,0.0,vec3(0.04),false,false);
        vec3 diffuse=vec3(0.0),specular=vec3(0.0);
        if(mode==7) AddTracedHandheldLighting(a.xyz,b.xyz,b.xyz,material,false,0.5,ivec2(0),diffuse,specular);
        else AddOldHandheldLighting(a.xyz,b.xyz,b.xyz,material,false,0.5,ivec2(0),diffuse,specular);
        out0=vec4(diffuse,1.0);
    }
    if(mode==11) {out0=rtHandheld.source[0];out1=rtHandheld.source[1];}
    if(mode==8) out0=vec4(RTTraceLocalVisibility(a.xyz,b.xyz),1.0);
    if(mode==9) out0=vec4(RTSceneOccluded(a.xyz,b.xyz)?vec3(0.0):RTTraceGlass(a.xyz,b.xyz),1.0);
    if(mode==10) { mat2x3 fog=RTRaymarchLocalFog(a.xyz,b.xyz,0.5,ivec2(0));out0=vec4(fog[0],fog[1].x); }
    outputData[2u*i]=out0; outputData[2u*i+1u]=out1;
}
''')
    GL.glUseProgram(shader)
    textures={}
    for unit,(name,path,width) in enumerate((('rtSceneShapesTex','scene_shapes.bin',4096),('rtSceneAlphaTex','scene_alpha.bin',32))):
        data=np.frombuffer((SHADERS/'texture/rt'/path).read_bytes(),dtype=np.uint32).copy()
        tex=GL.glGenTextures(1); textures[name]=int(tex)
        GL.glActiveTexture(GL.GL_TEXTURE0+unit);GL.glBindTexture(GL.GL_TEXTURE_2D,tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA32UI,width,len(data)//(4*width),0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,data)
        GL.glUniform1i(GL.glGetUniformLocation(shader,name),unit)
    hierarchy_tex=int(GL.glGenTextures(1))
    GL.glActiveTexture(GL.GL_TEXTURE4);GL.glBindTexture(GL.GL_TEXTURE_3D,hierarchy_tex)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_RGBA32UI,16,16,16,0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,np.zeros((16,16,16,4),np.uint32))
    GL.glUniform1i(GL.glGetUniformLocation(shader,'rtLocalHierarchyTex'),4)
    tiles_tex=int(GL.glGenTextures(1))
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA32UI,1,1,0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,np.array([1,0,0,0],np.uint32))
    GL.glUniform1i(GL.glGetUniformLocation(shader,'rtLightTilesTex'),5)
    builder=program('#version 460 compatibility\n'+BASE_MACROS+expand(SHADERS/'program/prepare/BuildLocalHierarchy.comp'))
    GL.glUseProgram(builder)
    for name,unit in (('rtSceneShapesTex',0),('rtSceneGridTex',3),('rtGlassGridTex',2),('rtLocalHierarchyImg',0)):
        GL.glUniform1i(GL.glGetUniformLocation(builder,name),unit)
    GL.glBindImageTexture(0,hierarchy_tex,0,GL.GL_TRUE,0,GL.GL_WRITE_ONLY,GL.GL_RGBA32UI)
    GL.glUseProgram(shader)
    grids={}
    for unit,name in ((2,'rtGlassGridTex'),(3,'rtSceneGridTex')):
        tex=GL.glGenTextures(1);grids[name]=int(tex)
        GL.glActiveTexture(GL.GL_TEXTURE0+unit);GL.glBindTexture(GL.GL_TEXTURE_3D,tex)
        GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
        GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_R32UI,64,64,64,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,np.zeros((64,64,64),np.uint32))
        GL.glUniform1i(GL.glGetUniformLocation(shader,name),unit)
    buffers={}
    for binding,size in ((4,16),(5,4112),(6,32),(7,32),(8,32)):
        buf=GL.glGenBuffers(1);buffers[binding]=int(buf)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buf)
        payload=np.zeros(size//4,np.uint32)
        if binding==4: payload[0]=1
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,size,payload,GL.GL_DYNAMIC_COPY)
        GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,binding,buf)
    for name in ('gbufferModelView','gbufferModelViewInverse'):
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(shader,name),1,GL.GL_FALSE,np.eye(4,dtype=np.float32))
    GL.glUniform3f(GL.glGetUniformLocation(shader,'cameraPosition'),0,0,0)

    resolver=program('#version 460 compatibility\n'+BASE_MACROS+expand(SHADERS/'program/prepare/ResolveHandheldPosition.comp'))
    GL.glUseProgram(resolver)
    for name,unit in (('rtSceneShapesTex',0),('rtSceneAlphaTex',1),('rtGlassGridTex',2),('rtSceneGridTex',3)):
        GL.glUniform1i(GL.glGetUniformLocation(resolver,name),unit)
    GL.glUseProgram(shader)
    def resolve(camera):
        flags={}
        for name in ('heldBlockLightValue','heldBlockLightValue2','isRightHanded'):
            value=np.zeros(1,np.int32);GL.glGetUniformiv(shader,GL.glGetUniformLocation(shader,name),value);flags[name]=int(value[0])
        matrix=np.zeros(16,np.float32);GL.glGetUniformfv(shader,GL.glGetUniformLocation(shader,'gbufferModelViewInverse'),matrix)
        GL.glUseProgram(resolver)
        for name,value in flags.items():GL.glUniform1i(GL.glGetUniformLocation(resolver,name),value)
        GL.glUniform3f(GL.glGetUniformLocation(resolver,'cameraPosition'),*camera)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(resolver,'gbufferModelViewInverse'),1,GL.GL_FALSE,matrix)
        GL.glDispatchCompute(1,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS);GL.glUseProgram(shader)

    def run(mode,rows,camera=(0,0,0)):
        if mode in (7,11,12):resolve(camera)
        data=np.array(rows,np.float32).reshape(-1,2,4)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'mode'),mode)
        GL.glUniform1ui(GL.glGetUniformLocation(shader,'queryCount'),len(data))
        GL.glUniform3f(GL.glGetUniformLocation(shader,'cameraPosition'),*camera)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[8]);GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,data,GL.GL_DYNAMIC_COPY)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[7]);GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,None,GL.GL_DYNAMIC_READ)
        GL.glDispatchCompute((len(data)+63)//64,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,data.nbytes),np.float32).copy().reshape(-1,2,4)

    tests=[]
    def record(name,ok,**detail):
        tests.append(dict(name=name,passed=bool(ok),**detail))
        if not ok: print('FAIL',name,detail,flush=True)

    selectors=json.loads((ROOT/'scripts/data/rt-alpha-selectors.json').read_text())
    with zipfile.ZipFile(JAR) as archive:
        # All 256 pixel columns, all facing/open/half variants for each trapdoor.
        for name in sorted({s.split(':')[1] for s in selectors if '_trapdoor' in s}):
            texture_name=name.removeprefix('waxed_')
            pixels=np.array(Image.open(io.BytesIO(archive.read(f'assets/minecraft/textures/block/{texture_name}.png'))).convert('RGBA'))[:,:,3]>=128
            blockstate=json.loads(archive.read(f'assets/minecraft/blockstates/{name}.json'))['variants']
            for state_key,variant in blockstate.items():
                state=dict(p.split('=') for p in state_key.split(','))
                selector='minecraft:'+name+''.join(':'+k+'='+v for k,v in sorted(state.items()))
                shape=selectors[selector]
                opened=state['open']=='true'
                model_name=variant['model'].removeprefix('minecraft:')
                model=json.loads(archive.read('assets/minecraft/models/'+model_name+'.json'))
                orientable='orientable' in model.get('parent','')
                truth=np.logical_or(pixels,pixels[:,::-1] if opened else pixels[::-1,:])
                if orientable: truth=np.logical_or(pixels,pixels[:,::-1])[::-1,:] if opened else pixels[::-1,:]
                rows=[]
                for y in range(16):
                    for x in range(16):
                        p=np.array([(x+.5)/16,(15-y+.5)/16,-.25] if opened else [(x+.5)/16,-.25,(y+.5)/16])
                        d=np.array([0,0,1] if opened else [0,1,0])
                        # Rotate around block centre, independently of the voxel builder.
                        angle=math.radians(variant.get('y',0));c,s=math.cos(angle),math.sin(angle)
                        rotation=np.array([[c,0,-s],[0,1,0],[s,0,c]])
                        ax=math.radians(variant.get('x',0));cx,sx=math.cos(ax),math.sin(ax)
                        rotation=rotation@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
                        p=rotation@(p-.5)+.5;d=rotation@d
                        rows.append([list(p)+[shape],list(d)+[1.5]])
                values=run(0,rows)[:,0,0].reshape(16,16)>.5
                record(selector,np.array_equal(values,truth),rays=256,holes=int((~truth).sum()),mismatches=int((values!=truth).sum()))

    fresnel_rows=[[[c,n,0,0],[0,0,0,0]] for c,n in ((1,1.5),(.5,1.5),(.001,1.5),(0,1),(math.sqrt(1-(1/1.5)**2),1/1.5),(.5,1/1.5))]
    f=run(1,fresnel_rows)[:,0,:]
    record('Fresnel normal incidence 4 percent',abs(float(f[0,0])-.04)<1e-5,result=f[0].tolist())
    record('Matched refractive index has zero reflection even at grazing angle',f[3,0]==0,result=f[3].tolist())
    record('Fresnel grazing and total internal reflection',f[2,0]>.98 and f[4,0]>.999 and f[5,0]>.999 and np.isfinite(f).all(),result=f.tolist())
    record('Fresnel reflection + transmission energy',np.allclose(f[:,0]+f[:,1],1),result=f[:,:2].tolist())

    absorption=run(2,[[[length,0,0,code],[0,0,0,0]] for code,length in ((15,1),(15,2),(15,.125),(12,1),(17,1))])[:,0,:3]
    record('Beer absorption multiplies across two blocks',np.allclose(absorption[1],absorption[0]**2,rtol=2e-5),result=absorption.tolist())
    record('Thin glass absorbs less than full glass',np.all(absorption[2]>absorption[0]),result=absorption[:3].tolist())
    record('Red and blue glass retain different spectra',absorption[0,0]>absorption[0,2] and absorption[3,2]>absorption[3,0],result=absorption[[0,3]].tolist())

    for code,thickness,front in ((17,1.0,0.0),(17|32|(10<<6),.125,.5625)):
        for angle in (0,10,20,30):
            theta=math.radians(angle);incoming=np.array([math.sin(theta),0,-math.cos(theta)])
            camera=(.5-incoming[0],.5,front-incoming[2]-1)
            result=run(3,[[list(incoming)+[code],[0,0,1,0]]],camera)[0]
            expected_length=thickness/math.sqrt(1-(math.sin(theta)/1.5)**2)
            record(f'Snell slab code {code} angle {angle}',np.allclose(result[0,:3],incoming,atol=3e-5) and abs(result[0,3]-expected_length)<3e-4 and result[1,3]>0,
                   direction=result[0,:3].tolist(),path=float(result[0,3]),expected_path=expected_length)

    falloff=run(4,[[[d*d,15,.1,0],[0,0,0,0]] for d in (0,1,2,4,8,14.99,15,16)])[:,0,0]
    record('Finite inverse-square emitter with smooth range',np.isfinite(falloff).all() and np.all(np.diff(falloff)<=0) and falloff[-2]==0 and falloff[-1]==0,result=falloff.tolist())

    def set_grid(name,cells):
        data=np.zeros((64,64,64),np.uint32)
        for (x,y,z),value in cells: data[z,y,x]=value
        GL.glActiveTexture(GL.GL_TEXTURE0+(2 if name=='rtGlassGridTex' else 3));GL.glBindTexture(GL.GL_TEXTURE_3D,grids[name])
        GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,data)
        GL.glUseProgram(builder);GL.glDispatchCompute(4,4,4);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS);GL.glUseProgram(shader)
    grid_results=[]
    for cells in ([],[((32,32,32),15)],[((32,32,32),15),((32,32,33),15)],[((32,32,32),15),((32,32,33),12)],[((32,32,32),17|32|(10<<6))]):
        set_grid('rtGlassGridTex',cells)
        grid_results.append(run(5,[[[.5,.5,-2,0],[.5,.5,3,0]]])[0,0,:3])
    g=np.array(grid_results)
    record('GPU multilayer glass grid',np.allclose(g[0],1) and np.allclose(g[1],absorption[0],rtol=1e-5) and np.allclose(g[2],g[1]**2,rtol=1e-5) and np.allclose(g[3],absorption[0]*absorption[3],rtol=1e-5),result=g.tolist())

    blockprops=(SHADERS/'block.properties').read_text()
    stone=next(int(i)-20000 for i,body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',blockprops,re.S) if 'minecraft:stone' in body.replace('\\',' ').split())
    set_grid('rtSceneGridTex',[((32,32,41),stone)])
    wall=run(6,[[[.5,.5,0,0],[.5,.5,14,0]],[[1.5,.5,0,0],[1.5,.5,14,0]]])[:,0,0]
    record('Opaque blocker beyond eight blocks and parallel clear ray',wall[0]==1 and wall[1]==0,result=wall.tolist())
    for name,value in (('heldBlockLightValue',15),('heldBlockLightValue2',0),('heldItemId',10001),('isRightHanded',1)):
        GL.glUniform1i(GL.glGetUniformLocation(shader,name),value)
    hand_rows=[[[.5,.5,-4,0],[0,0,1,0]]]
    set_grid('rtSceneGridTex',[])
    hand_clear=run(7,hand_rows)[0,0,:3]
    set_grid('rtSceneGridTex',[((32,32,30),stone)])
    hand_wall=run(7,hand_rows)[0,0,:3]
    set_grid('rtSceneGridTex',[((32,32,32),stone)])
    hand_beyond=run(7,hand_rows)[0,0,:3]
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldBlockLightValue'),0)
    hand_off=run(7,hand_rows)[0,0,:3]
    record('Handheld light blocked by wall, finite endpoint and switch off',hand_clear.max()>0 and hand_wall.max()==0 and np.allclose(hand_beyond,hand_clear) and hand_off.max()==0,
           clear=hand_clear.tolist(),blocked=hand_wall.tolist(),beyond=hand_beyond.tolist(),off=hand_off.tolist())
    from local_ray_v7_checks import run_v7_visibility_checks
    extra_tests,performance=run_v7_visibility_checks(run,set_grid,shader,buffers,hierarchy_tex,builder,stone)
    tests.extend(extra_tests)
    from handheld_v71_checks import run_handheld_checks
    tests.extend(run_handheld_checks(run,set_grid,shader,stone,resolver))
    from rt_v7_checks import run_v7_checks
    new_tests,local_performance=run_v7_checks(run,set_grid,shader,buffers,grids,textures,hierarchy_tex,tiles_tex)
    tests.extend(new_tests)
    performance["local_diffuse_pipeline"]=local_performance
    from validate_rt_glass import run_glass_tests
    tests.extend(run_glass_tests())
    tests.extend(shadow_alpha_tests())
    assert source_digest()==digest_before,'Sources changed during behavior probes'
    report={'source_digest':digest_before,'renderer':GL.glGetString(GL.GL_RENDERER).decode(),'passed':all(t['passed'] for t in tests),
            'behavior_checks':len(tests),'behavior_rays':sum(t.get('rays',0) for t in tests),
            'cutout_rays':sum(t.get('rays',0) for t in tests if t.get('name','').startswith('minecraft:') or t.get('name','')=='Aperture projection survives hierarchical traversal'),
            'runtime_game_validation':False,'performance':performance,'tests':tests}
    out=ROOT/'validation'/args.report_name;out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='tests'},indent=2),flush=True)
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']: raise SystemExit(1)

if __name__=='__main__':main()
