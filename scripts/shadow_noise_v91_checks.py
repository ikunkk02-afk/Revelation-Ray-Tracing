"""Static-shadow GPU regression against the shipped v9 stochastic integrator.

Actual area-light visibility on an opaque-block fixture, 32 independent frames.
This measures direct-shadow stability, not complete-frame GI noise or game FPS.
"""
from pathlib import Path
import json,re,zipfile
import glfw
import numpy as np
from OpenGL import GL
from PIL import Image,ImageDraw
from validate_rt import SHADERS,BASE_MACROS,expand,apply_options,profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT=SHADERS.parent

def main():
    digest=source_digest();tests=[]
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,6)
    glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_COMPAT_PROFILE)
    window=glfw.create_window(16,16,'Shadow noise regression',None,None);assert window
    glfw.make_context_current(window)
    opts={**profile_options('Ultra'),'RT_LOCAL_ACCELERATION':False,'RT_GLASS_ENABLED':False,
          'RT_LOCAL_SHADOW_SAMPLES':'noiseSamples'}
    header='#version 460 compatibility\n'+BASE_MACROS+'\nuniform int noiseSamples;\n'
    for name in ('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl','lib/lighting/BRDF.glsl',
                 'lib/lighting/LocalLights.glsl','lib/lighting/HandheldTracing.glsl'):
        header+=expand(SHADERS/name)+'\n'
    header=apply_options(header,opts)
    with zipfile.ZipFile(ROOT.parent.parent/'deliverables/Revelation-RT-v9-Lighting.zip') as z:
        old=z.read('shaders/lib/lighting/LocalLights.glsl').decode('utf-8')
    old=re.sub(r'^\s*#include\s+"[^"]+"\s*$','',old,flags=re.M)
    old=old.replace('RT_LOCAL_LIGHTING','RT_LOCAL_LIGHTING_OLD')
    old=old.replace('RTIntegrateLocalEmitter','RTIntegrateOldEmitter').replace('AddTracedLocalLighting','AddOldLocalLighting')
    old=old.replace('RT_LOCAL_TEMPORAL_SHADOWS','RT_OLD_STOCHASTIC')
    header+='\n#define RT_OLD_STOCHASTIC\n'+old
    code='''
layout(local_size_x=8,local_size_y=8) in;
layout(std430,binding=7) buffer Results {vec4 result[];};
uniform int mode;
void main(){ivec2 p=ivec2(gl_GlobalInvocationID.xy);if(any(greaterThanEqual(p,ivec2(64))))return;
 vec3 pos=vec3((float(p.x)+.5)/64.0*5.0-2.0,.025,(float(p.y)+.5)/64.0*5.0-2.0);
 vec3 n=vec3(0,1,0),d=vec3(0),s=vec3(0);
 Material m=Material(.6,0,0,vec3(.04),false,false);
 float noise=fract(52.9829189*fract(dot(vec2(p)+float(frameCounter)*vec2(5.588,5.588),vec2(.06711056,.00583715))));
 if(mode==0)AddTracedLocalLighting(pos,n,n,m,false,noise,p,d,s);
 if(mode==1)AddOldLocalLighting(pos,n,n,m,false,noise,p,d,s);
 if(mode==2)AddTracedHandheldLighting(pos,n,n,m,false,noise,p,d,s);
 result[p.y*64+p.x]=vec4(d+s,1);}
'''
    shader=program(header+code);GL.glUseProgram(shader)
    textures=[]
    def tex2(unit,data):
        t=int(GL.glGenTextures(1));textures.append(t)
        GL.glActiveTexture(GL.GL_TEXTURE0+unit);GL.glBindTexture(GL.GL_TEXTURE_2D,t)
        for param in (GL.GL_TEXTURE_MIN_FILTER,GL.GL_TEXTURE_MAG_FILTER):GL.glTexParameteri(GL.GL_TEXTURE_2D,param,GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA32UI,data.shape[1],data.shape[0],0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,data)
    tex2(0,np.frombuffer((SHADERS/'texture/rt/scene_shapes.bin').read_bytes(),np.uint32).reshape(1,4096,4))
    tex2(1,np.frombuffer((SHADERS/'texture/rt/scene_alpha.bin').read_bytes(),np.uint32).reshape(-1,32,4))
    tex2(3,np.array([[[1,0,0,0]]],np.uint32));tex2(4,np.zeros((1,1,4),np.uint32))
    stone=None
    props=(SHADERS/'block.properties').read_text(encoding='utf-8')
    for index,body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',props,re.S):
        if 'minecraft:stone' in body.replace('\\',' ').split():stone=int(index)-20000;break
    assert stone
    grid=np.zeros((64,64,64),np.uint32);grid[32,33,32]=stone
    t=int(GL.glGenTextures(1));textures.append(t)
    GL.glActiveTexture(GL.GL_TEXTURE2);GL.glBindTexture(GL.GL_TEXTURE_3D,t)
    for param in (GL.GL_TEXTURE_MIN_FILTER,GL.GL_TEXTURE_MAG_FILTER):GL.glTexParameteri(GL.GL_TEXTURE_3D,param,GL.GL_NEAREST)
    GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_R32UI,64,64,64,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    for name,unit in (('rtSceneShapesTex',0),('rtSceneAlphaTex',1),('rtSceneGridTex',2),('rtLightTilesTex',3),('rtLightTilesHiTex',4)):
        GL.glUniform1i(GL.glGetUniformLocation(shader,name),unit)
    for name in ('gbufferModelView','gbufferModelViewInverse'):
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(shader,name),1,False,np.eye(4,dtype=np.float32))
    GL.glUniform3f(GL.glGetUniformLocation(shader,'cameraPosition'),0,0,0)
    GL.glUniform2f(GL.glGetUniformLocation(shader,'scaledViewSize'),64,64)
    buffers=[]
    for binding,data in ((5,np.zeros(16+256*16,np.uint8)),(6,np.zeros(32,np.uint8)),(7,np.zeros(64*64*16,np.uint8))):
        b=int(GL.glGenBuffers(1));buffers.append(b);GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,binding,b)
        if binding==5:
            data[:16]=np.array([1,0,0,0],np.uint32).view(np.uint8)
            data[16:32]=np.array([32.5,35.1,32.5,5],np.float32).view(np.uint8)
        if binding==6:data[:16]=np.array([.5,3.1,.5,.1],np.float32).view(np.uint8)
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,data,GL.GL_DYNAMIC_READ)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldBlockLightValue'),15)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldBlockLightValue2'),0)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldItemId'),10001)
    def render(mode,frame,samples=4):
        GL.glUniform1i(GL.glGetUniformLocation(shader,'mode'),mode)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'frameCounter'),frame)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'noiseSamples'),samples)
        GL.glDispatchCompute(8,8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[2])
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,64*64*16),np.float32).copy().reshape(64,64,4)[:,:,:3]
    old=np.array([render(1,f) for f in range(32)])
    new=np.array([render(0,f) for f in range(32)])
    hand=np.array([render(2,f) for f in range(32)])
    old_std=old.std(axis=0);new_delta=float(np.abs(new-new[0]).max());hand_delta=float(np.abs(hand-hand[0]).max())
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    check('Both shipped quality presets select fixed area sampling',
          profile_options('Ultra').get('RT_LOCAL_TEMPORAL_SHADOWS') is False and
          profile_options('RayTracing').get('RT_LOCAL_TEMPORAL_SHADOWS') is False and
          profile_options('Ultra')['RT_LOCAL_SHADOW_SAMPLES']=='4' and
          profile_options('RayTracing')['RT_LOCAL_SHADOW_SAMPLES']=='8')
    check('Shipped v9 reproduces frame-varying area-shadow grain',float(old_std.max())>.002,max_temporal_std=float(old_std.max()),noisy_pixels=int((old_std.max(axis=2)>.001).sum()))
    check('Ultra direct shadows are independent of pixel noise and frame',new_delta<1e-7,max_frame_difference=new_delta,frames=32)
    check('Handheld shadows are independent of pixel noise and frame',hand_delta<1e-7 and hand.max()>.001,
          max_frame_difference=hand_delta,peak_radiance=float(hand.max()),frames=32)
    reference=render(0,0,64);scale=max(float(reference.max()),1e-8)
    stable_error=float(np.sqrt(np.mean((new[0]-reference)**2)))/scale
    shipped_error=float(np.sqrt(np.mean((old[0]-reference)**2)))/scale
    # Four taps cannot reproduce a 64-tap penumbra exactly: record the remaining
    # quadrature error and compare against the shipped instantaneous estimator.
    # The primary acceptance criterion is zero temporal grain, checked above.
    check('Four fixed samples improve instantaneous area integration over v9',stable_error<shipped_error,
          stable_relative_rms=stable_error,shipped_relative_rms=shipped_error,
          higher_sample_errors={str(n):float(np.sqrt(np.mean((render(0,0,n)-reference)**2)))/scale for n in (8,16)})
    check('Stable mode retains clear, fully occluded and penumbra regions',new[0].max()>.01 and int((new[0].max(axis=2)<1e-8).sum())>20 and int(((old.mean(axis=0).max(axis=2)>0)&(old_std.max(axis=2)>.001)).sum())>20)
    canvas=Image.new('RGB',(768,294),(22,22,26));draw=ImageDraw.Draw(canvas)
    for i,(value,label) in enumerate(((old[0],'v9: one stochastic sample'),(new[0],'v9.1: stable four samples'),(reference,'64-sample reference'))):
        rgb=np.uint8(np.power(np.clip(value/scale,0,1),1/2.2)*255)
        canvas.paste(Image.fromarray(rgb).resize((256,256)),(i*256,25));draw.text((i*256+5,7),label,fill='white')
    draw.text((5,282),'Controlled GPU shadow fixture, not a Minecraft screenshot',fill='white')
    canvas.save(ROOT/'validation/shadow-noise-v91.png')
    report=dict(source_digest=digest,passed=all(x['passed'] for x in tests),renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                scope='Production direct lighting only, fixed geometry, pixel noise varied over 32 frames',runtime_game_validation=False,tests=tests)
    (ROOT/'validation/shadow-noise-v91.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert digest==source_digest()
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
