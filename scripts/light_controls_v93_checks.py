"""GPU controls/beam regression using production lighting and actual blockers."""
import json
import glfw
import numpy as np
from OpenGL import GL
from validate_rt import SHADERS,BASE_MACROS,expand,apply_options,profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT=SHADERS.parent
POINTS=np.array([[0,0,-4,0],[4,0,-4,0],[0,0,2,0],[0,0,-20,0],[0,0,-31,0],
                 [2,0,-6,0],[0,0,0,0],[1.3,0,-4,0]],np.float32)

def main():
    digest=source_digest();tests=[]
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4);glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,6)
    glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_COMPAT_PROFILE)
    window=glfw.create_window(16,16,'Light control regression',None,None);assert window
    glfw.make_context_current(window)
    header='#version 460 compatibility\n'+BASE_MACROS+'''\n
layout(std430,binding=9) buffer Counts {uint shadowCounts[];};
uint queryIndex;
'''
    for name in ('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl','lib/lighting/BRDF.glsl','lib/lighting/Common.glsl',
                 'lib/lighting/HandheldTracing.glsl','lib/lighting/Emitters.glsl'):
        header+=expand(SHADERS/name)+'\n'
    signature='vec3 RTTraceLocalVisibility(vec3 playerOrigin,vec3 playerTarget,bool traceOpaque) {'
    assert signature in header
    header=header.replace(signature,signature+'\n atomicAdd(shadowCounts[queryIndex],1u);')
    body='''
layout(local_size_x=16) in;
layout(std430,binding=7) buffer Results {vec4 result[];};
layout(std430,binding=8) readonly buffer Points {vec4 positions[];};
uniform uint pointCount;
void main(){uint i=gl_GlobalInvocationID.x;if(i>=pointCount)return;queryIndex=i;
 vec3 p=positions[i].xyz;
 vec3 n=normalize(rtHandheld.source[0].xyz-p);
 Material m=Material(.6,0,0,vec3(.04),false,false);
 vec3 d=vec3(0),s=vec3(0);
 AddTracedHandheldLighting(p,n,n,m,false,.5,ivec2(i,0),d,s);
 result[i]=vec4(d+s,1);
 if(i==0u){
 result[pointCount]=vec4(RTEmitterColor(5u)*RTFalloff(16.0,15.0,RTEmitterRadius(5u)),1);
 result[pointCount+1u]=vec4(RTHeldColor(10005),1);
 result[pointCount+2u]=vec4(RTAdjustBlockEmission(vec3(.2,.4,.6)),1);
 result[pointCount+3u]=vec4(RTHandheldBeamFactor(heldItemId,vec3(0,0,-4)),
 RTHandheldBeamFactor(heldItemId,vec3(4,0,-4)),RTHandheldRange(heldItemId,15),1);}}
'''
    textures=[]
    def tex2(unit,data):
        t=int(GL.glGenTextures(1));textures.append(t);GL.glActiveTexture(GL.GL_TEXTURE0+unit)
        GL.glBindTexture(GL.GL_TEXTURE_2D,t)
        for param in (GL.GL_TEXTURE_MIN_FILTER,GL.GL_TEXTURE_MAG_FILTER):GL.glTexParameteri(GL.GL_TEXTURE_2D,param,GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA32UI,data.shape[1],data.shape[0],0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,data)
    tex2(0,np.frombuffer((SHADERS/'texture/rt/scene_shapes.bin').read_bytes(),np.uint32).reshape(1,4096,4))
    tex2(1,np.frombuffer((SHADERS/'texture/rt/scene_alpha.bin').read_bytes(),np.uint32).reshape(-1,32,4))
    grids={}
    for unit,name in ((2,'opaque'),(3,'glass')):
        t=int(GL.glGenTextures(1));textures.append(t);grids[name]=t
        GL.glActiveTexture(GL.GL_TEXTURE0+unit);GL.glBindTexture(GL.GL_TEXTURE_3D,t)
        for param in (GL.GL_TEXTURE_MIN_FILTER,GL.GL_TEXTURE_MAG_FILTER):GL.glTexParameteri(GL.GL_TEXTURE_3D,param,GL.GL_NEAREST)
        GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_R32UI,64,64,64,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,np.zeros((64,64,64),np.uint32))
    buffers={}
    for binding,data in ((5,np.zeros(4112,np.uint8)),(6,np.array([[-.35,-.2,-.55,.05],[.35,-.2,-.55,.05]],np.float32)),
                         (7,np.zeros((len(POINTS)+4,4),np.float32)),(8,POINTS),(9,np.zeros(len(POINTS),np.uint32))):
        b=int(GL.glGenBuffers(1));buffers[binding]=b;GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,binding,b)
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,data,GL.GL_DYNAMIC_READ)
    opts={**profile_options('Ultra'),'RT_LOCAL_ACCELERATION':False,'RT_GLASS_ENABLED':True}
    cache={}
    def run(options=None,item=10005,offhand=False):
        options=options or {};key=tuple(sorted(options.items()))
        if key not in cache:cache[key]=program(apply_options(header+body,{**opts,**options}))
        p=cache[key];GL.glUseProgram(p)
        for name,unit in (('rtSceneShapesTex',0),('rtSceneAlphaTex',1),('rtSceneGridTex',2),('rtGlassGridTex',3)):
            GL.glUniform1i(GL.glGetUniformLocation(p,name),unit)
        for name in ('gbufferModelView','gbufferModelViewInverse'):
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(p,name),1,False,np.eye(4,dtype=np.float32))
        GL.glUniform3f(GL.glGetUniformLocation(p,'cameraPosition'),0,0,0)
        for name,value in (('heldItemId',item),('heldItemId2',item),('heldBlockLightValue',0 if offhand else 15),('heldBlockLightValue2',15 if offhand else 0)):
            GL.glUniform1i(GL.glGetUniformLocation(p,name),value)
        GL.glUniform1ui(GL.glGetUniformLocation(p,'pointCount'),len(POINTS))
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[9]);GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,len(POINTS)*4,np.zeros(len(POINTS),np.uint32))
        GL.glDispatchCompute(1,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[7])
        out=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,(len(POINTS)+4)*16),np.float32).copy().reshape(-1,4)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[9])
        counts=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,len(POINTS)*4),np.uint32).copy()
        assert np.isfinite(out).all()
        return out,counts
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    n=len(POINTS);base,base_counts=run()
    check('Default v9.2 torch intensity and color retained',base[0,:3].max()>.01 and np.allclose(base[n+1,:3],np.array([1,.6,.22])@np.array([[.6274413721,.0690276171,.0163642351],[.3292974595,.9195806669,.0880171625],[.0433514584,.0113614226,.8955649727]]),atol=2e-6))
    check('Natural torch and lantern retain the same prior palette',np.allclose(run(item=10001)[0][:n],base[:n],atol=1e-6))
    check('Omnidirectional torch still lights outside the future beam',base[1,:3].max()>0 and base[2,:3].max()>0)
    block_off,_=run({'BLOCKLIGHT_BRIGHTNESS':'0.0'})
    check('Block brightness zero removes source radiance and emission',np.all(block_off[n,:3]==0) and np.all(block_off[n+2,:3]==0))
    check('Block brightness no longer changes handheld brightness',np.allclose(block_off[:n],base[:n],atol=1e-6))
    block_two,_=run({'BLOCKLIGHT_BRIGHTNESS':'2.0'})
    check('Block brightness scales direct radiance and emission linearly',np.allclose(block_two[[n,n+2],:3],base[[n,n+2],:3]*2,rtol=1e-6))
    red_block,_=run({'RT_BLOCK_CUSTOM_COLOR':True,'BLOCKLIGHT_COLOR_R':'1.00','BLOCKLIGHT_COLOR_G':'0.00','BLOCKLIGHT_COLOR_B':'0.00'})
    check('Custom block color reaches both direct light and source emission',all(red_block[i,0]>red_block[i,1]*4 and red_block[i,0]>red_block[i,2]*8 for i in (n,n+2)))
    check('Custom block color does not tint held light',np.allclose(red_block[:n],base[:n],atol=1e-6))
    blue_hand,_=run({'HELD_LIGHT_CUSTOM_COLOR':True,'HELD_LIGHT_COLOR_R':'0.00','HELD_LIGHT_COLOR_G':'0.00','HELD_LIGHT_COLOR_B':'1.00'})
    check('Custom handheld color reaches actual surface illumination',blue_hand[0,2]>blue_hand[0,0]*8 and np.allclose(blue_hand[n,:3],base[n,:3],atol=1e-6))
    doubled,_=run({'HELD_LIGHT_BRIGHTNESS':'1.0'})
    check('Handheld brightness scales independently and linearly',np.allclose(doubled[:n,:3],base[:n,:3]*2,rtol=1e-6))
    hand_off,off_counts=run({'HELD_LIGHT_BRIGHTNESS':'0.0'})
    check('Zero handheld brightness avoids both illumination and shadow rays',np.all(hand_off[:n,:3]==0) and np.all(off_counts==0))
    flash_opts={'RT_HANDHELD_FLASHLIGHT':True,'HELD_LIGHT_CUSTOM_COLOR':True,'HELD_LIGHT_COLOR_R':'1.00','HELD_LIGHT_COLOR_G':'1.00','HELD_LIGHT_COLOR_B':'1.00'}
    flash,counts=run(flash_opts)
    check('Flashlight lights the crosshair but not its sides or behind it',flash[0,:3].max()>0 and flash[1,:3].max()==0 and flash[2,:3].max()==0)
    check('Flashlight extends to configured range with a finite cutoff',base[3,:3].max()==0 and flash[3,:3].max()>0 and flash[4,:3].max()==0)
    check('Flashlight retains one shadow ray; outside-beam pixels trace none',counts[0]==1 and counts[1]==0 and counts[2]==0,per_point_counts=counts.tolist())
    check('All three torch types enter beam mode',all(run(flash_opts,item=i)[0][1,:3].max()==0 for i in (10005,10006,10007)))
    check('Lanterns and luminous blocks remain omnidirectional',all(run(flash_opts,item=i)[0][1,:3].max()>0 for i in (10001,10002,10003,10004)))
    check('Offhand torch also supports the flashlight',run(flash_opts,offhand=True)[0][0,:3].max()>0 and run(flash_opts,offhand=True)[0][1,:3].max()==0)
    narrow,_=run({**flash_opts,'RT_FLASHLIGHT_FOV':'20.0'})
    wide,_=run({**flash_opts,'RT_FLASHLIGHT_FOV':'60.0'})
    check('Beam field of view changes the illuminated region',narrow[5,:3].max()==0 and wide[5,:3].max()>0)
    hard,_=run({**flash_opts,'RT_FLASHLIGHT_SOFTNESS':'0.0'})
    check('Softness zero is finite and softness fades only the rim',hard[7,:3].max()>flash[7,:3].max() and np.allclose(hard[0],flash[0]))
    # A solid panel between receiver and resolved hand source must stop the beam.
    import re
    props=(SHADERS/'block.properties').read_text(encoding='utf-8')
    stone=next(int(i)-20000 for i,b in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',props,re.S) if 'minecraft:stone' in b.replace('\\',' ').split())
    grid=np.zeros((64,64,64),np.uint32);grid[30,24:40,24:40]=stone
    GL.glActiveTexture(GL.GL_TEXTURE2);GL.glBindTexture(GL.GL_TEXTURE_3D,grids['opaque'])
    GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    blocked,_=run(flash_opts)
    check('Flashlight remains occluded by a solid wall',blocked[0,:3].max()==0)
    grid.fill(0);GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    grid[30,24:40,24:40]=15
    GL.glActiveTexture(GL.GL_TEXTURE3);GL.glBindTexture(GL.GL_TEXTURE_3D,grids['glass'])
    GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    tinted,_=run(flash_opts)
    check('Flashlight retains stained-glass absorption and tint',tinted[0,0]>tinted[0,2]*2 and np.all(tinted[0,:3]<flash[0,:3]))
    report=dict(source_digest=digest,passed=all(t['passed'] for t in tests),renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                runtime_game_validation=False,tests=tests,scope='Production light controls, handheld illumination, beam rejection, ray counts and real opaque/glass traversal')
    assert digest==source_digest()
    (ROOT/'validation/light-controls-v93.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
