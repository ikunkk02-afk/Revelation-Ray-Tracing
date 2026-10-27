"""Single-projection GPU regression against the shipped v9.1 area-tap integrator.

Actual area-light visibility on an opaque-block fixture, 32 independent frames.
This measures direct-shadow stability, not complete-frame GI noise or game FPS.
"""
from pathlib import Path
import argparse,json,re,zipfile
import glfw
import numpy as np
from OpenGL import GL
from PIL import Image,ImageDraw
from validate_rt import SHADERS,BASE_MACROS,expand,apply_options,profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT=SHADERS.parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report-name',default='shadow-projection-v92.json')
    parser.add_argument('--preview-name',default='shadow-projection-v92.png')
    args=parser.parse_args()
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
    header='#version 460 compatibility\n'+BASE_MACROS+'\nuniform int noiseSamples;\nlayout(std430,binding=8) buffer Counters { uint shadowRayCount; };\n'
    for name in ('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl','lib/lighting/BRDF.glsl',
                 'lib/lighting/LocalLights.glsl','lib/lighting/HandheldTracing.glsl'):
        header+=expand(SHADERS/name)+'\n'
    header=apply_options(header,opts)
    signature='vec3 RTTraceLocalVisibility(vec3 playerOrigin,vec3 playerTarget,bool traceOpaque) {'
    assert header.count(signature)>=1
    header=header.replace(signature,signature+'\n atomicAdd(shadowRayCount,1u);')

    with zipfile.ZipFile(ROOT.parent.parent/'deliverables/Revelation-RT-v9.1-StableShadows.zip') as z:
        old=z.read('shaders/lib/lighting/LocalLights.glsl').decode('utf-8')
    old=re.sub(r'^\s*#include\s+"[^"]+"\s*$','',old,flags=re.M)
    old=old.replace('RT_LOCAL_LIGHTING','RT_LOCAL_LIGHTING_OLD')
    old=old.replace('RTIntegrateLocalEmitter','RTIntegrateOldEmitter').replace('AddTracedLocalLighting','AddOldLocalLighting')
    old=old.replace('RT_LOCAL_TEMPORAL_SHADOWS','RT_OLD_STOCHASTIC')
    old=old.replace('RT_LOCAL_SOFT_SHADOWS','RT_OLD_SOFT')
    header+='\n#define RT_OLD_SOFT\n'+old
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
 if(mode==3){vec3 delta=vec3(.5,3.1,.5)-pos;float dist2=dot(delta,delta);
 d=RTEmitterColor(5u)*RTFalloff(dist2,15.0,RTEmitterRadius(5u))*max(0.0,delta.y*inversesqrt(dist2));}
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
    for binding,data in ((5,np.zeros(16+256*16,np.uint8)),(6,np.zeros(32,np.uint8)),(7,np.zeros(64*64*16,np.uint8)),(8,np.zeros(16,np.uint8))):
        b=int(GL.glGenBuffers(1));buffers.append(b);GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,binding,b)
        if binding==5:
            data[:16]=np.array([1,0,0,0],np.uint32).view(np.uint8)
            data[16:32]=np.array([32.5,35.1,32.5,5],np.float32).view(np.uint8)
        if binding==6:data[:16]=np.array([.5,3.1,.5,.1],np.float32).view(np.uint8)
        GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,data,GL.GL_DYNAMIC_READ)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldBlockLightValue'),15)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldBlockLightValue2'),0)
    GL.glUniform1i(GL.glGetUniformLocation(shader,'heldItemId'),10001)
    trace_counts={}
    def render(mode,frame,samples=4):
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[3])
        GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4,np.zeros(1,np.uint32))
        GL.glUniform1i(GL.glGetUniformLocation(shader,'mode'),mode)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'frameCounter'),frame)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'noiseSamples'),samples)
        GL.glDispatchCompute(8,8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[2])
        value=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,64*64*16),np.float32).copy().reshape(64,64,4)[:,:,:3]
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[3])
        trace_counts[(mode,frame,samples)]=int(np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4),np.uint32)[0])
        return value
    old=np.array([render(1,f) for f in range(32)])
    new=np.array([render(0,f) for f in range(32)])
    hand=np.array([render(2,f) for f in range(32)])
    old_std=old.std(axis=0);new_delta=float(np.abs(new-new[0]).max());hand_delta=float(np.abs(hand-hand[0]).max())
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    check('Ultra and RT presets use a single placed and handheld projection',
          all(profile_options(p).get('RT_LOCAL_SOFT_SHADOWS') is False and
              profile_options(p).get('RT_LOCAL_TEMPORAL_SHADOWS') is False and
              profile_options(p)['RT_LOCAL_SHADOW_SAMPLES']=='1' and
              profile_options(p)['RT_HANDHELD_SOFT_SAMPLES']=='1' for p in ('Ultra','RayTracing')))
    reference=render(3,0);scale=max(float(reference.max()),1e-8)
    y,x=np.mgrid[0:64,0:64]
    origins=np.stack(((x+.5)/64*5-2,np.full((64,64),.033),(y+.5)/64*5-2),axis=2)
    delta=np.array([.5,3.1,.5])-origins
    a=(np.array([0.,1.,0.])-origins)/delta;b=(np.array([1.,2.,1.])-origins)/delta
    entry=np.minimum(a,b).max(axis=2);leave=np.maximum(a,b).min(axis=2)
    blocked=(leave>np.maximum(entry,0))&(entry<1)&(leave>0)
    expected=reference*(~blocked)[:,:,None]
    error=float(np.abs(new[0]-expected).max())
    check('Single-source shadow agrees with independent CPU segment-box projection',error<1e-6,max_absolute_error=error)
    old_ratio=old[0,:,:,0]/np.maximum(reference[:,:,0],1e-8)
    new_ratio=new[0,:,:,0]/np.maximum(reference[:,:,0],1e-8)
    old_partial=int(((old_ratio>.001)&(old_ratio<.999)).sum())
    new_partial=int(((new_ratio>.001)&(new_ratio<.999)).sum())
    check('Shipped v9.1 reproduces several offset partial projections',old_partial>100,partial_pixels=old_partial)
    check('Default has no displaced quarter-strength shadow copies',new_partial==0,partial_pixels=new_partial)
    check('Single projection remains stable over 32 frames',new_delta==0,max_frame_difference=new_delta)
    check('Handheld uses one stable projection with nonzero illumination',hand_delta==0 and hand.max()>.001,max_frame_difference=hand_delta)
    old_rays=trace_counts[(1,0,4)];new_rays=trace_counts[(0,0,4)]
    check('One lamp traces one shadow ray instead of four',new_rays==64*64 and old_rays==4*new_rays,
          v91_shadow_rays=old_rays,v92_shadow_rays=new_rays,whole_game_fps_measured=False)
    check('Fully occluded and illuminated regions are both retained',new[0].max()>.01 and blocked.sum()>20 and (~blocked).sum()>20)
    # Reproduce the user's aperture case with the actual vanilla oak-trapdoor
    # model/PNG, not just a featureless cube. CPU segment/voxel intersections
    # are independent of the GPU DDA and its packed alpha texture.
    from rt_alpha_geometry import AlphaGeometry
    jar=Path(r'D:\HMCL\.minecraft\versions\1.21.1-fabric\1.21.1-fabric.jar')
    with zipfile.ZipFile(jar) as archive:
        variants=json.loads(archive.read('assets/minecraft/blockstates/oak_trapdoor.json'))['variants']
        variant=next(value for key,value in variants.items()
                     if all(dict(token.split('=') for token in key.split(',')).get(k)==v
                            for k,v in {'facing':'north','half':'bottom','open':'false'}.items()))
        occupied=AlphaGeometry(archive).voxels(variant)
    selector='minecraft:oak_trapdoor:facing=north:half=bottom:open=false'
    trapdoor=next(int(index)-20000 for index,body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',props,re.S)
                  if selector in body.replace('\\',' ').split())
    grid.fill(0);grid[32,33,32]=trapdoor
    GL.glActiveTexture(GL.GL_TEXTURE2);GL.glBindTexture(GL.GL_TEXTURE_3D,t)
    GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    trap_current=render(0,0);trap_old=render(1,0)
    trap_blocked=np.zeros((64,64),bool)
    voxels=np.array(sorted(occupied),np.float64)/16+np.array([0,1,0])
    for begin in range(0,len(voxels),64):
        lo=voxels[begin:begin+64]
        aa=(lo[None,None,:,:]-origins[:,:,None,:])/delta[:,:,None,:]
        bb=(lo[None,None,:,:]+1/16-origins[:,:,None,:])/delta[:,:,None,:]
        tin=np.minimum(aa,bb).max(axis=3);tout=np.maximum(aa,bb).min(axis=3)
        trap_blocked|=((tout>np.maximum(tin,0))&(tin<1)&(tout>0)).any(axis=2)
    trap_expected=reference*(~trap_blocked)[:,:,None]
    trap_error=float(np.abs(trap_current-trap_expected).max())
    check('Oak-trapdoor projection matches independent vanilla-alpha CPU rays',trap_error<1e-6,
          max_absolute_error=trap_error,receiver_rays=4096,opaque_model_voxels=len(occupied))
    trap_ratio=trap_current[:,:,0]/np.maximum(reference[:,:,0],1e-8)
    check('Oak-trapdoor apertures retain one full-strength projection per lamp',
          not ((trap_ratio>.001)&(trap_ratio<.999)).any() and trap_blocked.sum()>20 and (~trap_blocked).sum()>20)
    old[0]=trap_old;new[0]=trap_current;expected=trap_expected
    canvas=Image.new('RGB',(768,294),(22,22,26));draw=ImageDraw.Draw(canvas)
    for i,(value,label) in enumerate(((old[0],'v9.1: four offset projections'),(new[0],'v9.2: single projection'),(expected,'Independent CPU projection'))):
        rgb=np.uint8(np.power(np.clip(value/scale,0,1),1/2.2)*255)
        canvas.paste(Image.fromarray(rgb).resize((256,256)),(i*256,25));draw.text((i*256+5,7),label,fill='white')
    draw.text((5,282),'Controlled GPU shadow fixture, not a Minecraft screenshot',fill='white')
    canvas.save(ROOT/'validation'/args.preview_name)
    report=dict(source_digest=digest,passed=all(x['passed'] for x in tests),renderer=GL.glGetString(GL.GL_RENDERER).decode(),
                scope='Single-lamp production direct lighting; v9.1 failing control; independent CPU projection; actual shadow-ray counters; 32-frame stability',runtime_game_validation=False,tests=tests)
    (ROOT/'validation'/args.report_name).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    assert digest==source_digest()
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
