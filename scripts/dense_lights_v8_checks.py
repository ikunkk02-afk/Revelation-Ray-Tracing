"""GPU regression for the actual tiled selector, all-light integrator and fog.

Uses the shipped v7.1 integrator as a failing control. No Minecraft is launched.
"""
from pathlib import Path
import argparse, json, re, zipfile
import glfw
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw
from validate_rt import SHADERS, BASE_MACROS, expand, source, apply_options, profile_options
from validate_rt_glass import program
from rt_source_digest import source_digest

ROOT=SHADERS.parent


def blackbody_chroma(kelvin: float) -> np.ndarray:
    """Same Planckian fit and sRGB primaries the shader uses."""
    t = min(max(kelvin, 1000.0), 15000.0)
    t2, t3 = t * t, t * t * t
    x = (-0.2661239e9 / t3 - 0.2343589e6 / t2 + 0.8776956e3 / t + 0.179910) if t <= 4000 else         (-3.0258469e9 / t3 + 2.1070379e6 / t2 + 0.2226347e3 / t + 0.240390)
    x2, x3 = x * x, x * x * x
    if t <= 2222:
        y = -1.1063814 * x3 - 1.34811020 * x2 + 2.18555832 * x - 0.20219683
    elif t <= 4000:
        y = -0.9549476 * x3 - 1.37418593 * x2 + 2.09137015 * x - 0.16748867
    else:
        y = 3.0817580 * x3 - 5.87338670 * x2 + 3.75112997 * x - 0.37001483
    xyz = np.array([x / y, 1.0, (1.0 - x - y) / y])
    rgb = np.array([xyz @ np.array([3.2404542, -1.5371385, -0.4985314]),
                    xyz @ np.array([-0.9692660, 1.8760108, 0.0415560]),
                    xyz @ np.array([0.0556434, -0.2040259, 1.0572252])])
    rgb = np.maximum(rgb, 0.0)
    return rgb / max(rgb.max(), 1e-5)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report-name',default='dense-lights-v8.json')
    parser.add_argument('--preview-name',default='dense-lights-v8.png')
    args=parser.parse_args()
    digest=source_digest()
    assert glfw.init()
    glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,6)
    glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_COMPAT_PROFILE)
    window=glfw.create_window(32,32,'RT v8 dense light regression',None,None)
    assert window
    glfw.make_context_current(window)
    # Analytic shipped path: the mask must reproduce the exhaustive sum exactly.
    options={**profile_options('RayTracing'),'RT_GLASS_ENABLED':False,'RT_LOCAL_ACCELERATION':False,'RT_LOCAL_VOLUMETRICS':True,'RT_LOCAL_SOFT_SHADOWS':True,
             'RT_LOCAL_SHADOW_SAMPLES':'testSamples','RT_LOCAL_TRACED_SHADOWS':False,
             'RT_LOCAL_TEMPORAL_SHADOWS':False}
    selector=program(source(SHADERS/'world0/deferred.csh',options))
    header='#version 460 compatibility\n'+BASE_MACROS+'\nuniform int testSamples;\n'
    for name in ('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/Transform.glsl',
                 'lib/surface/Material.glsl','lib/lighting/BRDF.glsl','lib/lighting/LocalLights.glsl',
                 'lib/lighting/LocalVolumetrics.glsl'):
        header+=expand(SHADERS/name)+'\n'
    with zipfile.ZipFile(ROOT.parent.parent/'deliverables/Revelation-RT-v7.1-HandheldFix.zip') as z:
        old=z.read('shaders/lib/lighting/LocalLights.glsl').decode('utf-8')
    old=re.sub(r'^\s*#include\s+"([^"]+)"\s*$',lambda m:expand(SHADERS/m[1].lstrip('/')),old,flags=re.M)
    old=old.replace('RT_LOCAL_LIGHTING','RT_LOCAL_LIGHTING_OLD').replace('AddTracedLocalLighting','AddOldLocalLighting')
    header+='''uniform usampler2D rtOldTilesTex;
uvec4 RTLightIndices(ivec2 pixel) {return texelFetch(rtOldTilesTex,clamp(pixel/16,ivec2(0),textureSize(rtOldTilesTex,0)-1),0);}
'''+old
    shader=program(apply_options(header+'''
layout(local_size_x=8,local_size_y=8) in;
layout(std430,binding=7) writeonly buffer Results {vec4 result[];};
uniform int mode;
void main(){
    ivec2 pixel=ivec2(gl_GlobalInvocationID.xy);
    if(any(greaterThanEqual(pixel,ivec2(scaledViewSize))))return;
    vec2 uv=(vec2(pixel)+0.5)*scaledTexelSize;
    vec4 clip=gbufferProjection*vec4(0,0,-4,1);
    vec3 pos=ScreenToViewPos(vec3(uv,clip.z/clip.w*.5+.5));
    vec3 n=vec3(0,0,1),d=vec3(0),s=vec3(0);
    Material material=Material(.5,0,0,vec3(.04),false,false);
    if(mode==0) AddTracedLocalLighting(pos,n,n,material,false,.5,pixel,d,s);
    if(mode==1) {
        vec3 player=transMAD(gbufferModelViewInverse,pos);
        for(uint i=0u;i<min(rtScene.lightCount,rtMaxLights);++i)
            RTIntegrateLocalEmitter(i,player,player+n*max(.008,abs(pos.z)*8e-5),n,n,normalize(-pos),material,.5,d,s);
    }
    if(mode==2) AddOldLocalLighting(pos,n,n,material,false,.5,pixel,d,s);
    if(mode==3) d=RTRaymarchLocalFog(vec3(0),pos,.5,pixel)[0];
    if(mode==5) d=RTEmitterColor(11u);
    result[pixel.y*int(scaledViewSize.x)+pixel.x]=vec4(d,1);
}
''',options))
    textures=[]
    def tex2(unit,data,internal=GL.GL_RGBA32UI,fmt=GL.GL_RGBA_INTEGER,kind=GL.GL_UNSIGNED_INT):
        tex=int(GL.glGenTextures(1));textures.append(tex)
        GL.glActiveTexture(GL.GL_TEXTURE0+unit);GL.glBindTexture(GL.GL_TEXTURE_2D,tex)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
        GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
        GL.glTexImage2D(GL.GL_TEXTURE_2D,0,internal,data.shape[1],data.shape[0],0,fmt,kind,data)
        return tex
    tex2(0,np.frombuffer((SHADERS/'texture/rt/scene_shapes.bin').read_bytes(),np.uint32).reshape(1,4096,4))
    tex2(1,np.frombuffer((SHADERS/'texture/rt/scene_alpha.bin').read_bytes(),np.uint32).reshape(-1,32,4))
    scene=int(GL.glGenTextures(1));textures.append(scene)
    GL.glActiveTexture(GL.GL_TEXTURE2);GL.glBindTexture(GL.GL_TEXTURE_3D,scene)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_3D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    grid=np.zeros((64,64,64),np.uint32)
    GL.glTexImage3D(GL.GL_TEXTURE_3D,0,GL.GL_R32UI,64,64,64,0,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    buffers=GL.glGenBuffers(2)
    for binding,buffer in zip((5,7),buffers):GL.glBindBufferBase(GL.GL_SHADER_STORAGE_BUFFER,binding,int(buffer))
    projection=np.array([[1,0,0,0],[0,1,0,0],[0,0,-(64+.1)/(64-.1),-2*64*.1/(64-.1)],[0,0,-1,0]],np.float32)
    tests=[]
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    def set_lights(lights):
        data=np.zeros(16+256*16,np.uint8)
        data[:16]=np.array([len(lights),0,0,0],np.uint32).view(np.uint8)
        values=np.array(lights,np.float32).copy();values[:,:3]+=32
        data[16:16+len(values)*16]=values.view(np.uint8).reshape(-1)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,int(buffers[0]));GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,data.nbytes,data,GL.GL_DYNAMIC_DRAW)
    def setup(width,height,lights,camera=(0,0,0)):
        tw=max(width//16,1);th=max(height//16,1)
        low=tex2(3,np.zeros((th,tw,4),np.uint32));high=tex2(4,np.zeros((th,tw,4),np.uint32))
        # The original selector chose the four nearest sources to the tile's
        # centre. A constant-depth wall makes its five depth probes equivalent.
        oldtiles=np.zeros((th,tw,4),np.uint32)
        for y in range(th):
            for x in range(tw):
                receiver=np.array([((min(x*16+8,width-1)+.5)/width*2-1)*4,((min(y*16+8,height-1)+.5)/height*2-1)*4,-4])
                order=np.argsort(np.sum((np.array(lights)[:,:3]-receiver)**2,axis=1),kind='stable')[:4]+1
                oldtiles[y,x,:len(order)]=order
        old=tex2(5,oldtiles)
        for p in (selector,shader):
            GL.glUseProgram(p)
            for name,unit in (('rtSceneShapesTex',0),('rtSceneAlphaTex',1),('rtSceneGridTex',2),('rtLightTilesTex',3),('rtLightTilesHiTex',4),('rtOldTilesTex',5),('rtLightTilesImg',0),('rtLightTilesHiImg',1)):
                GL.glUniform1i(GL.glGetUniformLocation(p,name),unit)
            for name,value in (('gbufferModelView',np.eye(4,dtype=np.float32)),('gbufferModelViewInverse',np.eye(4,dtype=np.float32)),('gbufferProjection',projection),('gbufferProjectionInverse',np.linalg.inv(projection))):
                GL.glUniformMatrix4fv(GL.glGetUniformLocation(p,name),1,GL.GL_TRUE,value)
            GL.glUniform2f(GL.glGetUniformLocation(p,'scaledViewSize'),width,height)
            GL.glUniform2f(GL.glGetUniformLocation(p,'scaledTexelSize'),1/width,1/height)
            GL.glUniform3f(GL.glGetUniformLocation(p,'cameraPosition'),*camera)
        set_lights(lights)
        GL.glBindImageTexture(0,low,0,False,0,GL.GL_WRITE_ONLY,GL.GL_RGBA32UI)
        GL.glBindImageTexture(1,high,0,False,0,GL.GL_WRITE_ONLY,GL.GL_RGBA32UI)
        GL.glUseProgram(selector);GL.glDispatchCompute((tw+7)//8,(th+7)//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,int(buffers[1]));GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,width*height*16,None,GL.GL_DYNAMIC_READ)
    def run(width,height,mode=0,samples=1):
        GL.glUseProgram(shader)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'mode'),mode)
        GL.glUniform1i(GL.glGetUniformLocation(shader,'testSamples'),samples)
        GL.glDispatchCompute((width+7)//8,(height+7)//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,int(buffers[1]))
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,width*height*16),np.float32).reshape(height,width,4)[:,:,:3].copy()
    rng=np.random.default_rng(405)
    for count in (4,9,36,129,256):
        lights=np.column_stack((rng.uniform(-8,8,count),rng.uniform(-6,6,count),rng.uniform(-2.5,1,count),np.full(count,11))).astype(np.float32)
        w,h=(129,65) if count==9 else (64,48)
        setup(w,h,lights)
        actual=run(w,h);expected=run(w,h,1)
        err=float(np.max(np.abs(actual-expected)))
        check(f'All {count} lights match exhaustive GPU integration, including tile edges and tail',np.isfinite(actual).all() and err<2e-4,max_error=err,pixels=w*h)
        # Independent inverse-square, Lambert cosine and finite-range reference.
        yy,xx=np.mgrid[:h,:w]
        pos=np.stack(((xx+.5)/w*8-4,(yy+.5)/h*8-4,np.full((h,w),-4)),axis=-1)
        delta=lights[None,None,:,:3]-pos[:,:,None,:]
        dist2=np.sum(delta**2,axis=-1)
        # Physical kernel: finite Lambertian disc, flux normalised, colour from the
        # emitter's colour temperature (kind 11 = 5600 K), Rec.2020 primaries.
        # Kernel validated against an independent CPU formula; the emitter colour
        # itself is read back from the shader so the Planckian fit is not
        # re-derived (and can be tested on its own).
        emitter_color = run(w, h, 5)[0, 0].astype(np.float64)
        radius, emitter_range = 0.04, 15.0
        falloff_window=np.clip(1-(dist2/(emitter_range*emitter_range))**2,0,1)**2
        scalar=np.sum(falloff_window/(np.pi*np.maximum(dist2,radius*radius))*np.clip(delta[:,:,:,2]/np.sqrt(dist2),0,1),axis=-1)
        cpu=scalar[:,:,None]*emitter_color
        cpuerr=float(np.max(np.abs(cpu-actual)))
        check(f'{count} lights match independent inverse-square and cosine reference',cpuerr<2e-4,
              max_error=cpuerr,cpu_peak=float(cpu.max()),gpu_peak=float(actual.max()),
              ratio=float(cpu.max()/max(actual.max(),1e-9)))
        if count==9:
            old=run(w,h,2)
            old_error=float(np.max(np.abs(old-expected)))
            check('Shipped v7.1 control loses clustered-light energy; v8 restores it',
              old_error>0.05*float(cpu.max()) and err<old_error*.001,old_error=old_error,new_error=err,
              control_error_share_of_peak=old_error/float(max(cpu.max(),1e-9)))
            # Equal display transfer for both panels. This is a GPU lab figure.
            panels=[]
            for rgb in (old,actual):
                display=np.power(np.clip(rgb/(1+rgb),0,1),1/2.2)
                panels.append(Image.fromarray(np.uint8(display*255)).resize((516,260)))
            canvas=Image.new('RGB',(1032,300),(18,18,18));draw=ImageDraw.Draw(canvas)
            for i,panel in enumerate(panels):canvas.paste(panel,(i*516,28))
            draw.text((8,8),'v7.1: nearest 4 lamps',fill='white');draw.text((524,8),'v8: all 9 lamps; same exposure',fill='white')
            draw.text((8,286),'Controlled GPU receiver - not a Minecraft screenshot',fill='white')
            canvas.save(ROOT/'validation'/args.preview_name)
        if count==36:
            shuffled=lights[rng.permutation(count)]
            setup(w,h,shuffled);reordered=run(w,h)
            check('Light insertion order does not change the image',np.max(np.abs(actual-reordered))<2e-4)
    # Area-light sample positions remain tied to absolute sources when their
    # insertion order changes, even with actual opaque occluders in the grid.
    lights=np.array([[-2,2,-1,11],[2,2,-1,11],[0,-2,-1,11],[3,1,-2,11],[-3,1,-2,11]],np.float32)
    props=(SHADERS/'block.properties').read_text(encoding='utf-8')
    stone=next(int(i)-20000 for i,body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',props,re.S) if 'minecraft:stone' in body.replace('\\',' ').split())
    grid[29:32,31:34,31:33]=stone
    GL.glActiveTexture(GL.GL_TEXTURE2);GL.glBindTexture(GL.GL_TEXTURE_3D,scene)
    GL.glTexSubImage3D(GL.GL_TEXTURE_3D,0,0,0,0,64,64,64,GL.GL_RED_INTEGER,GL.GL_UNSIGNED_INT,grid)
    setup(48,32,lights);area=run(48,32,0,16);reference=run(48,32,1,16)
    check('16-sample multi-light soft shadows match exhaustive integration',np.max(np.abs(area-reference))<2e-4 and np.isfinite(area).all())
    setup(48,32,lights[::-1]);reverse=run(48,32,0,16)
    check('Area-shadow pattern is independent of atomic light insertion order',np.max(np.abs(area-reverse))<2e-4)
    # In-scattering must add linearly; extinction is independent of lamp count.
    setup(16,16,lights);fog=run(16,16,3)
    individual=[]
    for light in lights:
        setup(16,16,light[None]);individual.append(run(16,16,3))
    check('Multiple volumetric lights add without nearest-light switching',np.max(np.abs(fog-np.sum(individual,axis=0)))<2e-5 and np.isfinite(fog).all() and np.max(fog)>0)
    assert source_digest()==digest,'Sources changed during dense-light tests'
    report={'source_digest':digest,'renderer':GL.glGetString(GL.GL_RENDERER).decode(),'passed':all(t['passed'] for t in tests),'runtime_game_validation':False,'tests':tests}
    (ROOT/'validation'/args.report_name).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    glfw.destroy_window(window);glfw.terminate()
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
