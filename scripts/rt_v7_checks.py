"""GPU checks of v7 production programs. Controlled fixtures, not game FPS."""
import json, statistics
import numpy as np
from OpenGL import GL
from validate_rt import BASE_MACROS, SHADERS, expand, source, profile_options
from validate_rt_glass import program


def texture2d(unit, data, internal=GL.GL_RGBA32F, fmt=GL.GL_RGBA, dtype=GL.GL_FLOAT):
    tex=int(GL.glGenTextures(1)); GL.glActiveTexture(GL.GL_TEXTURE0+unit)
    GL.glBindTexture(GL.GL_TEXTURE_2D,tex)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MIN_FILTER,GL.GL_NEAREST)
    GL.glTexParameteri(GL.GL_TEXTURE_2D,GL.GL_TEXTURE_MAG_FILTER,GL.GL_NEAREST)
    GL.glTexImage2D(GL.GL_TEXTURE_2D,0,internal,data.shape[1],data.shape[0],0,fmt,dtype,data)
    return tex


def fragment_program(text, vertex=None):
    if vertex is None:
        vertex='''#version 460 compatibility
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2-1,0,1);}'''
    p=GL.glCreateProgram()
    for stage,s in ((GL.GL_VERTEX_SHADER,vertex),(GL.GL_FRAGMENT_SHADER,text)):
        sh=GL.glCreateShader(stage);GL.glShaderSource(sh,s);GL.glCompileShader(sh)
        assert GL.glGetShaderiv(sh,GL.GL_COMPILE_STATUS),GL.glGetShaderInfoLog(sh)
        GL.glAttachShader(p,sh);GL.glDeleteShader(sh)
    GL.glLinkProgram(p);assert GL.glGetProgramiv(p,GL.GL_LINK_STATUS),GL.glGetProgramInfoLog(p)
    return p


def run_v7_checks(run,set_grid,original,buffers,grids,textures,hierarchy_tex,tiles_tex):
    tests=[]
    def check(name,ok,**details):
        tests.append(dict(name=name,passed=bool(ok),**details))
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    # Compare spectral separation with the shipped v6 default, independently
    # reconstructed from its published palette and transmission-space blend.
    spectra=run(2,[[[1,0,0,i],[0,0,0,0]] for i in range(1,18)])[:,0,:3]
    check('All 16 dye spectra and clear glass conserve energy',np.isfinite(spectra).all() and (spectra>0).all() and (spectra<=1).all())
    old_red=np.array([.95,.12,.08]);linear=((old_red+.055)*.94786729)**2.4
    matrix=np.array([[.6274413721,.3292974595,.0433514584],[.0690276171,.9195806669,.0113614226],[.0163642351,.0880171625,.8955649727]])
    old=.985*.35+np.clip(matrix@linear,.01,.985)*.65
    check('Red glass spectral separation exceeds v6 default',spectra[14,0]/spectra[14,1]>old[0]/old[1]*1.5,
          v6_ratio=float(old[0]/old[1]),v7_ratio=float(spectra[14,0]/spectra[14,1]))
    check('Clear glass retains 98.5 percent bulk transmission',np.allclose(spectra[16],.985,atol=2e-6))

    # Render the real Basic fragment to both actual output formats, prefilled
    # with invalid PBR data so an unwritten channel cannot accidentally pass.
    opts={**profile_options('RayTracing'),'RT_LOCAL_HALF_RES':True,'RT_LOCAL_SHADOW_SAMPLES':'4'}
    basic=fragment_program(source(SHADERS/'world0/gbuffers_basic.fsh',opts),'''#version 460 compatibility
flat out vec4 vertColor;flat out uint selectionOverlay;out vec2 lightmap;uniform uint selected;
void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2-1,0,1);vertColor=vec4(.5,.5,.5,1);selectionOverlay=selected;lightmap=vec2(0);}''')
    fbo=int(GL.glGenFramebuffers(1));GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,fbo)
    albedo=texture2d(7,np.zeros((3,3,4),np.float32),GL.GL_RGBA16F)
    packed=texture2d(8,np.full((3,3,4),65535,np.uint32),GL.GL_RGBA16UI,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT)
    for i,t in enumerate((albedo,packed)):GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER,GL.GL_COLOR_ATTACHMENT0+i,GL.GL_TEXTURE_2D,t,0)
    GL.glDrawBuffers([GL.GL_COLOR_ATTACHMENT0,GL.GL_COLOR_ATTACHMENT1])
    assert GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)==GL.GL_FRAMEBUFFER_COMPLETE
    GL.glViewport(0,0,3,3);GL.glDisable(GL.GL_DEPTH_TEST);GL.glDisable(GL.GL_BLEND)
    GL.glUseProgram(basic);GL.glUniform1f(GL.glGetUniformLocation(basic,'alphaTestRef'),.1)
    GL.glUniform2f(GL.glGetUniformLocation(basic,'scaledViewSize'),3,3)
    for selected in (0,1):
        GL.glUniform1ui(GL.glGetUniformLocation(basic,'selected'),selected);GL.glDrawArrays(GL.GL_TRIANGLES,0,3)
        GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT1)
        value=np.frombuffer(GL.glReadPixels(1,1,1,1,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT),np.uint32)
        check('Basic writes complete PBR material: '+str(selected),np.array_equal(value,[0,501 if selected else 1,0,0]),result=value.tolist())

    # Actual post fragments: flood the input radiance, yet selection must stay
    # at display RGB .05 rather than receive exposure, bloom or sharpening.
    GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER,GL.GL_COLOR_ATTACHMENT1,GL.GL_TEXTURE_2D,0,0)
    GL.glDrawBuffers([GL.GL_COLOR_ATTACHMENT0])
    bright=texture2d(10,np.full((3,3,4),1000,np.float32))
    for entry in ('composite31.fsh','final.fsh'):
        p=fragment_program(source(SHADERS/'world0'/entry,opts));GL.glUseProgram(p)
        for name,unit in (('colortex7',8),('colortex0',10),('colortex1',10),('colortex4',10)):
            GL.glUniform1i(GL.glGetUniformLocation(p,name),unit)
        for name,value in (('scaledViewSize',3.),('originViewSize',3.),('originTexelSize',1/3)):
            GL.glUniform2f(GL.glGetUniformLocation(p,name),value,value)
        GL.glDrawArrays(GL.GL_TRIANGLES,0,3);GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
        value=np.frombuffer(GL.glReadPixels(1,1,1,1,GL.GL_RGBA,GL.GL_FLOAT),np.float32)[:3]
        check('Selection survives '+entry+' without glow',np.allclose(value,.05,atol=.0001),result=value.tolist())
        GL.glDeleteProgram(p)
    GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,0);GL.glDeleteProgram(basic)

    raw=(SHADERS/'program/post/Final.frag').read_text()
    cas=raw[raw.index('vec3 FFXCasFilter'):raw.index('#include "/lib/universal/TextRenderer')]
    header='#version 460 compatibility\n'+BASE_MACROS+expand(SHADERS/'lib/Utility.glsl')+expand(SHADERS/'lib/universal/Uniform.glsl')
    cp=program(header+cas+'''layout(local_size_x=1) in;layout(std430,binding=7) buffer Result{vec4 value;};void main(){value=vec4(FFXCasFilter(ivec2(1),.3),1);}''')
    GL.glUseProgram(cp);GL.glUniform1i(GL.glGetUniformLocation(cp,'colortex0'),10)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[7]);GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,16,None,GL.GL_DYNAMIC_READ)
    for name,arr in [('black',np.zeros((3,3,4),np.float32)),('dark',np.full((3,3,4),.0001,np.float32)),('thin bright line',np.zeros((3,3,4),np.float32))]:
        if name=='thin bright line':arr[:,1,:]=.8
        GL.glActiveTexture(GL.GL_TEXTURE10);GL.glBindTexture(GL.GL_TEXTURE_2D,bright)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,3,3,GL.GL_RGBA,GL.GL_FLOAT,arr)
        GL.glDispatchCompute(1,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        value=np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16),np.float32)[:3]
        check('CAS finite and bounded: '+name,np.isfinite(value).all() and (value>=arr[:,:,:3].min()-1e-6).all() and (value<=arr[:,:,:3].max()+1e-6).all(),result=value.tolist())
    GL.glDeleteProgram(cp)

    # Exercise the production cache producer, gather and native fallback with
    # the same local light integrator. Timer includes both optimized dispatches.
    producer=program(source(SHADERS/'world0/deferred20.csh',opts))
    includes=('lib/Utility.glsl','lib/universal/Uniform.glsl','lib/universal/SSBO.glsl','lib/universal/Transform.glsl','lib/universal/Fetch.glsl','lib/universal/Random.glsl','lib/surface/Material.glsl','lib/lighting/BRDF.glsl','lib/lighting/HandheldTracing.glsl','lib/lighting/LocalLights.glsl','lib/lighting/LocalLightCache.glsl')
    from validate_rt import apply_options
    header=apply_options('#version 460 compatibility\n'+BASE_MACROS+'\n'.join(expand(SHADERS/i) for i in includes),opts)
    consumer=program(header+'''
layout(local_size_x=8,local_size_y=8) in;
layout(std430,binding=7) buffer Results { vec4 result[]; };
uniform bool cachedMode;
void main(){
 ivec2 p=ivec2(gl_GlobalInvocationID.xy);if(any(greaterThanEqual(p,ivec2(scaledViewSize))))return;
 vec3 pos=ScreenToViewPos(vec3((vec2(p)+.5)*scaledTexelSize,loadDepth0(p)));
 vec3 geo,n;FetchNormalData(p,geo,n);Material m=GetMaterialData(ExtractSpecularTex(loadMaterialPack(p)),FetchBaseColor(p));
 vec3 d=vec3(0),s=vec3(0);bool reused=false;
 if(cachedMode)reused=RTGatherLocalDiffuse(p,pos,n,m,d,s);
 if(!reused){d=vec3(0);float noise=BlueNoise(p,frameCounter);AddTracedHandheldLighting(pos,n,geo,m,false,noise,p,d,s);AddTracedLocalLighting(pos,n,geo,m,false,noise,p,d,s);}
 result[p.y*int(scaledViewSize.x)+p.x]=vec4(d+s,float(reused));
}''')
    size=256;half=size//2
    projection=np.array([[1,0,0,0],[0,1,0,0],[0,0,-(64+.1)/(64-.1),-2*64*.1/(64-.1)],[0,0,-1,0]],np.float32)
    clip=projection@np.array([0,0,-4,1],np.float32);depth=(clip[2]/clip[3]+1)*.5
    cache=texture2d(11,np.zeros((half,half,4),np.float32),GL.GL_RGBA16F)
    spec_cache=texture2d(12,np.zeros((half,half,4),np.float32),GL.GL_RGBA16F)
    normal=texture2d(9,np.zeros((size,size,4),np.float32),GL.GL_RGBA16F)
    texture2d(7,np.full((size,size,4),.5,np.float32),GL.GL_RGBA16F)
    packdata=np.zeros((size,size,4),np.uint32);packdata[:,:,1]=1
    material=texture2d(8,packdata,GL.GL_RGBA16UI,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT)
    depthdata=np.full((size,size),depth,np.float32)
    depthtex=texture2d(10,depthdata,GL.GL_R32F,GL.GL_RED)
    texture2d(6,np.full((256,256,4),.5,np.float32),GL.GL_RGBA16F)
    tiles=np.tile(np.array([1,0,0,0],np.uint32),(16,16,1))
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexImage2D(GL.GL_TEXTURE_2D,0,GL.GL_RGBA32UI,16,16,0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,tiles)
    set_grid('rtSceneGridTex',[]);set_grid('rtGlassGridTex',[])
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[5]);GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16,np.array([1,0,0,0],np.uint32))
    GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,16,16,np.array([32,32,31,7],np.float32))
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[7]);GL.glBufferData(GL.GL_SHADER_STORAGE_BUFFER,size*size*16,None,GL.GL_DYNAMIC_READ)
    for p in (producer,consumer):
        GL.glUseProgram(p)
        for name,unit in (('rtSceneShapesTex',0),('rtSceneAlphaTex',1),('rtGlassGridTex',2),('rtSceneGridTex',3),('rtLocalHierarchyTex',4),('rtLightTilesTex',5),('noisetex',6),('colortex6',7),('colortex7',8),('colortex8',9),('depthtex0',10),('rtLocalDiffuseTex',11),('rtLocalDiffuseImg',0),('rtLocalSpecularTex',12),('rtLocalSpecularImg',1)):
            GL.glUniform1i(GL.glGetUniformLocation(p,name),unit)
        for name,value in (('scaledViewSize',size),('scaledHalfViewSize',half),('scaledTexelSize',1/size)):
            GL.glUniform2f(GL.glGetUniformLocation(p,name),value,value)
        for name,value in (('gbufferModelView',np.eye(4,dtype=np.float32)),('gbufferModelViewInverse',np.eye(4,dtype=np.float32)),('gbufferProjection',projection),('gbufferProjectionInverse',np.linalg.inv(projection))):
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(p,name),1,GL.GL_TRUE,value)
        GL.glUniform1i(GL.glGetUniformLocation(p,'heldBlockLightValue'),0)
        GL.glUniform1i(GL.glGetUniformLocation(p,'heldBlockLightValue2'),0)
    GL.glBindImageTexture(0,cache,0,GL.GL_FALSE,0,GL.GL_WRITE_ONLY,GL.GL_RGBA16F)
    GL.glBindImageTexture(1,spec_cache,0,GL.GL_FALSE,0,GL.GL_WRITE_ONLY,GL.GL_RGBA16F)
    def dispatch(cached):
        if cached:
            GL.glUseProgram(producer);GL.glDispatchCompute(half//8,half//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glUseProgram(consumer);GL.glUniform1i(GL.glGetUniformLocation(consumer,'cachedMode'),cached)
        GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    def read():
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[7])
        return np.frombuffer(GL.glGetBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,size*size*16),np.float32).copy().reshape(size,size,4)
    dispatch(False);native=read();dispatch(True);cached=read()
    reuse=float(cached[:,:,3].mean());error=float(np.abs(cached[:,:,:3]-native[:,:,:3]).max())
    check('Production half-res producer and gather preserve smooth receiver',np.isfinite(cached).all() and native[:,:,:3].max()>.01 and reuse>.8 and error<.004,reused_fraction=reuse,max_absolute_error=error)
    # A normal rough dielectric (LabPBR F0 = 10/255) used to be classified as
    # metal and bypass the coarse producer. Exercise both diffuse and GGX now.
    pbrpack=packdata.copy();pbrpack[:,:,2]=115|(10<<8)
    GL.glActiveTexture(GL.GL_TEXTURE8);GL.glBindTexture(GL.GL_TEXTURE_2D,material)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,pbrpack)
    dispatch(False);pbr_native=read();dispatch(True);pbr_cached=read()
    pbr_error=float(np.abs(pbr_cached[:,:,:3]-pbr_native[:,:,:3]).max())
    pbr_reuse=float(pbr_cached[:,:,3].mean())
    check('Rough PBR reuses diffuse and GGX without double counting',np.isfinite(pbr_cached).all() and pbr_reuse>.8 and pbr_error<.008,
          reused_fraction=pbr_reuse,max_absolute_error=pbr_error)
    # Same depth/normal, different material: only full-resolution evaluation is
    # valid. Bright coarse samples must not cross a metal/dielectric boundary.
    mixed=pbrpack.copy();mixed[::2,::2,2]=115|(255<<8)
    GL.glActiveTexture(GL.GL_TEXTURE8);GL.glBindTexture(GL.GL_TEXTURE_2D,material)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,mixed)
    GL.glUseProgram(consumer);GL.glUniform1i(GL.glGetUniformLocation(consumer,'cachedMode'),1)
    GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    check('Material boundary rejects coarse highlight reuse',read()[::2,::2,3].max()==0)
    GL.glActiveTexture(GL.GL_TEXTURE8);GL.glBindTexture(GL.GL_TEXTURE_2D,material)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,packdata)
    dispatch(True)
    # A traced set larger than the old top-four budget must equal the sum of
    # rendering each lamp alone, and must not depend on SSBO insertion order.
    many_lamps=np.array([[30+4*i/11,33+(i%3)*.2,31,11] for i in range(12)],np.float32)
    many_tiles=tiles.copy();many_tiles[:,:,0]=(1<<12)-1
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,16,16,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,many_tiles)
    def lamps(values):
        GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[5])
        GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16,np.array([len(values),0,0,0],np.uint32))
        GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,16,values.nbytes,values)
    lamps(many_lamps);dispatch(False);many=read()[:,:,:3]
    individual=np.zeros_like(many)
    for lamp in many_lamps:
        lamps(lamp.reshape(1,4));dispatch(False);individual+=read()[:,:,:3]
    many_error=float(np.abs(many-individual).max())
    check('Twelve traced lamps equal the sum of twelve independent renders',many.max()>.01 and many_error<2e-5,max_absolute_error=many_error)
    lamps(many_lamps[::-1].copy());dispatch(False);reverse=read()[:,:,:3]
    check('Traced multi-light energy is independent of insertion order',np.allclose(reverse,many,atol=2e-5))
    lamps(np.array([[32,32,31,7]],np.float32))
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,16,16,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,tiles)
    dispatch(True)
    # Stale samples on a different plane or facing a different normal must
    # trigger native tracing rather than leak light through an edge.
    GL.glActiveTexture(GL.GL_TEXTURE11);GL.glBindTexture(GL.GL_TEXTURE_2D,cache)
    fixture=np.full((half,half,4),100,np.float32);fixture[:,:,3]=-9
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,half,half,GL.GL_RGBA,GL.GL_FLOAT,fixture)
    GL.glUseProgram(consumer);GL.glUniform1i(GL.glGetUniformLocation(consumer,'cachedMode'),1);GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    rejected=read()
    check('Different depth planes reject cached lighting',rejected[:,:,3].max()==0 and np.allclose(rejected,native,atol=1e-6))
    fixture[:,:,:3]=[4,0,0];fixture[:,half//2:,:3]=[0,0,4];fixture[:,:,3]=-4
    GL.glActiveTexture(GL.GL_TEXTURE11);GL.glBindTexture(GL.GL_TEXTURE_2D,cache)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,half,half,GL.GL_RGBA,GL.GL_FLOAT,fixture)
    GL.glUseProgram(consumer);GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    boundary=read()
    check('Sharp red-blue light boundary falls back to native tracing',boundary[:,size//2,3].max()==0 and np.allclose(boundary[:,size//2,:3],native[:,size//2,:3],atol=1e-6))
    # A normal discontinuity must also reject a nearby sample on the same plane.
    normals=np.zeros((size,size,4),np.float32);normals[1::2,1::2,:]=1
    GL.glActiveTexture(GL.GL_TEXTURE9);GL.glBindTexture(GL.GL_TEXTURE_2D,normal)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA,GL.GL_FLOAT,normals)
    GL.glUseProgram(consumer);GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    normal_edge=read()
    check('Different surface normals reject cached lighting',normal_edge[::2,::2,3].max()==0)
    normals.fill(0);GL.glActiveTexture(GL.GL_TEXTURE9);GL.glBindTexture(GL.GL_TEXTURE_2D,normal)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA,GL.GL_FLOAT,normals)
    # An empty light tile must ignore even deliberately bright stale cache data.
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,16,16,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,np.zeros_like(tiles))
    GL.glUseProgram(consumer);GL.glDispatchCompute(size//8,size//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    unlit=read()
    check('Unlit tiles bypass reconstruction and ignore stale cache',np.all(unlit[:,:,:3]==0) and np.all(unlit[:,:,3]==1))
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,16,16,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,tiles)
    # Invalid producer markers at selection, sky and polished PBR pixels.
    original_pack=packdata.copy();packdata[:64,:,1]=501;packdata[64:128,:,1]=0;packdata[128:192,:,2]=255
    GL.glActiveTexture(GL.GL_TEXTURE8);GL.glBindTexture(GL.GL_TEXTURE_2D,material)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,packdata)
    GL.glUseProgram(producer);GL.glDispatchCompute(half//8,half//8,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
    GL.glActiveTexture(GL.GL_TEXTURE11);GL.glBindTexture(GL.GL_TEXTURE_2D,cache)
    markers=np.frombuffer(GL.glGetTexImage(GL.GL_TEXTURE_2D,0,GL.GL_RGBA,GL.GL_FLOAT),np.float32).reshape(half,half,4)[:,:,3]
    check('Selection, sky and polished PBR excluded from coarse producer',np.all(markers[:96]==0) and np.all(markers[96:]<0))
    GL.glActiveTexture(GL.GL_TEXTURE8);GL.glBindTexture(GL.GL_TEXTURE_2D,material)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,size,size,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,original_pack)
    for _ in range(3):dispatch(False);dispatch(True)
    times={False:[],True:[]};query=int(np.asarray(GL.glGenQueries(1)).reshape(-1)[0])
    for _ in range(9):
        for mode in (False,True):
            GL.glBeginQuery(GL.GL_TIME_ELAPSED,query);dispatch(mode);GL.glEndQuery(GL.GL_TIME_ELAPSED)
            times[mode].append(float(GL.glGetQueryObjectuiv(query,GL.GL_QUERY_RESULT))*1e-6)
    performance={'scope':'256x256 controlled rough receiver, one warm emitter (kind 7), no occluders; production local-light functions and cache producer/gather; not Minecraft FPS',
                 'native_samples_ms':times[False],'cached_samples_ms':times[True],'native_median_ms':statistics.median(times[False]),'cached_median_ms':statistics.median(times[True]),
                 'speedup':statistics.median(times[False])/statistics.median(times[True]),'reused_fraction':reuse,'max_absolute_error':error}
    GL.glActiveTexture(GL.GL_TEXTURE5);GL.glBindTexture(GL.GL_TEXTURE_2D,tiles_tex)
    GL.glTexSubImage2D(GL.GL_TEXTURE_2D,0,0,0,16,16,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT,np.zeros_like(tiles))
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[5]);GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4,np.array([0],np.uint32))
    empty_times={False:[],True:[]}
    for _ in range(3):dispatch(False);dispatch(True)
    for _ in range(9):
        for mode in (False,True):
            GL.glBeginQuery(GL.GL_TIME_ELAPSED,query);dispatch(mode);GL.glEndQuery(GL.GL_TIME_ELAPSED)
            empty_times[mode].append(float(GL.glGetQueryObjectuiv(query,GL.GL_QUERY_RESULT))*1e-6)
    performance['empty_tiles']={'native_samples_ms':empty_times[False],'cached_samples_ms':empty_times[True],
        'native_median_ms':statistics.median(empty_times[False]),'cached_median_ms':statistics.median(empty_times[True])}
    GL.glDeleteQueries(1,[query])
    (SHADERS.parent/'validation/performance-v7-local.json').write_text(json.dumps(performance,indent=2)+'\n',encoding='utf-8')
    GL.glUseProgram(original)
    return tests,performance
