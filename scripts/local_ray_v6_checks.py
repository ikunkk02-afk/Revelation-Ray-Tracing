"""Correctness and GPU elapsed-time probes for v6 visibility, not game FPS."""
from pathlib import Path
import hashlib, json, re, statistics, zipfile
import numpy as np
from OpenGL import GL
from PIL import Image, ImageDraw
from validate_rt import SHADERS


def run_v6_checks(run,set_grid,shader,buffers,hierarchy_tex,builder,stone):
    tests=[]
    def check(name,ok,**detail):
        tests.append(dict(name=name,passed=bool(ok),**detail))
        if not ok:print('FAIL',name,detail,flush=True)
    set_grid('rtGlassGridTex',[])
    set_grid('rtSceneGridTex',[((32,32,32),stone)])
    terminal=run(8,[[[.5,.5,-2,0],[.5,.5,.5,0]],[[1.5,.5,-2,0],[1.5,.5,.5,0]]])[:,0,:3]
    check('Opaque terminal cell blocks; adjacent clear ray remains open',np.max(terminal[0])==0 and np.allclose(terminal[1],1),result=terminal.tolist())
    # Exact boundary entry, negative coordinates, finite endpoint and tiny rays.
    edge=run(8,[[[.5,.5,-2,0],[.5,.5,-.001,0]],[[-.5,.5,-2,0],[-.5,.5,2,0]],[[.5,.5,1.001,0],[.5,.5,4,0]],[[.5,.5,-2,0],[.5,.5,-2,0]]])[:,0,:3]
    check('Finite endpoints, reverse clear segment and zero-length ray',np.allclose(edge,1),result=edge.tolist())
    set_grid('rtSceneGridTex',[])
    set_grid('rtGlassGridTex',[((32,32,32),15),((32,32,33),12)])
    rows=[[[.5,.5,-2,0],[.5,.5,3,0]],[[.5,.5,3,0],[.5,.5,-2,0]]]
    current=run(8,rows)[:,0,:3];reference=run(9,rows)[:,0,:3]
    check('Combined traversal preserves layered glass and reciprocal paths',np.allclose(current,reference,rtol=3e-4,atol=3e-5) and np.allclose(current[0],current[1]),current=current.tolist(),reference=reference.tolist())

    blockprops=(SHADERS/'block.properties').read_text()
    def class_for(selector):
        return next(int(i)-20000 for i,body in re.findall(r'block\.(\d+)\s*=\s*(.*?)(?=\nblock\.|\Z)',blockprops,re.S) if selector in body.replace('\\',' ').split())
    cage=class_for('minecraft:iron_trapdoor:facing=north:half=bottom:open=true')
    emitter=class_for('minecraft:glowstone')
    set_grid('rtGlassGridTex',[])
    set_grid('rtSceneGridTex',[((32,32,32),emitter)])
    own=run(8,[[[.5,.5,-2,0],[.5,.5,.5,0]]])[0,0,:3]
    check('Solid emitting cell does not occlude its own source',np.allclose(own,1),result=own.tolist())
    set_grid('rtSceneGridTex',[((32,32,32),cage)])
    size=128
    yy,xx=np.mgrid[0:size,0:size]
    origins=np.stack([-1.8+xx*4.6/(size-1),-1.8+yy*4.6/(size-1),np.full_like(xx,-2,dtype=np.float64)],axis=-1)
    data=np.zeros((size*size,2,4),np.float32);data[:,0,:3]=origins.reshape(-1,3);data[:,1,:3]=[.5,.5,2.0]
    aperture=run(8,data)[:,0,:3]
    baseline=run(9,data)[:,0,:3]
    holes=int(np.count_nonzero(aperture[:,0]>.5));blocked=int(np.count_nonzero(aperture[:,0]<.5))
    check('Aperture projection survives hierarchical traversal',np.allclose(aperture,baseline,atol=1e-5) and holes>100 and blocked>100,rays=size*size,lit=holes,blocked=blocked)
    # A laboratory visibility image, explicitly labelled as a controlled probe.
    attenuation=1/(1+np.sum((data[:,0,:3]-data[:,1,:3])**2,axis=1))
    pattern=(.45+.12*((xx//4+yy//4)%2)).reshape(-1)
    values=(aperture*(attenuation*pattern*25)[:,None])
    srgb=np.clip(values,0,1)**(1/2.2)
    picture=Image.fromarray((srgb.reshape(size,size,3)[::-1]*255).astype(np.uint8)).resize((512,512),Image.Resampling.NEAREST)
    canvas=Image.new('RGB',(512,548),(20,20,20));canvas.paste(picture,(0,0))
    ImageDraw.Draw(canvas).text((8,519),'GPU aperture probe - not a Minecraft screenshot',fill=(220,220,220))
    canvas.save(SHADERS.parent/'validation/v6-aperture-probe.png')

    timings=[]
    source_table=np.frombuffer((SHADERS/'texture/rt/scene_shapes.bin').read_bytes(),np.uint32).reshape(-1,4)
    def gpu_time(mode,count,repeats=9):
        GL.glUseProgram(shader);GL.glUniform1i(GL.glGetUniformLocation(shader,'mode'),mode)
        GL.glUniform1ui(GL.glGetUniformLocation(shader,'queryCount'),count)
        for _ in range(3):GL.glDispatchCompute((count+63)//64,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        GL.glFinish()
        query=int(np.asarray(GL.glGenQueries(1)).reshape(-1)[0]);values=[]
        for _ in range(repeats):
            GL.glBeginQuery(GL.GL_TIME_ELAPSED,query)
            GL.glDispatchCompute((count+63)//64,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
            GL.glEndQuery(GL.GL_TIME_ELAPSED)
            values.append(float(GL.glGetQueryObjectuiv(query,GL.GL_QUERY_RESULT))*1e-6)
        GL.glDeleteQueries(1,[query]);return values
    def build_time():
        GL.glUseProgram(builder)
        q=int(np.asarray(GL.glGenQueries(1)).reshape(-1)[0]);values=[]
        for _ in range(9):
            GL.glBeginQuery(GL.GL_TIME_ELAPSED,q);GL.glDispatchCompute(4,4,4);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS);GL.glEndQuery(GL.GL_TIME_ELAPSED)
            values.append(float(GL.glGetQueryObjectuiv(q,GL.GL_QUERY_RESULT))*1e-6)
        GL.glDeleteQueries(1,[q]);GL.glUseProgram(shader);return statistics.median(values)
    nside=512
    y,x=np.mgrid[0:nside,0:nside]
    for name,width,length in (('sparse_room',12.,12.),('narrow_cave',2.4,15.)):
        scene=[((a,31,b),stone) for a in range(17,48) for b in range(14,49)]
        if name=='sparse_room':
            scene += [((a,b,37),stone) for a in range(31,35) for b in range(32,37)]
        else:
            scene += [((a,b,c),stone) for a in (29,35) for b in range(32,38) for c in range(14,49)]
            scene += [((32,b,39),stone) for b in range(32,36)]
        glass=[((a,b,36),12) for a in range(27,31) for b in range(32,36)]
        set_grid('rtSceneGridTex',scene);set_grid('rtGlassGridTex',glass)
        GL.glActiveTexture(GL.GL_TEXTURE4);GL.glBindTexture(GL.GL_TEXTURE_3D,hierarchy_tex)
        actual=np.frombuffer(GL.glGetTexImage(GL.GL_TEXTURE_3D,0,GL.GL_RGBA_INTEGER,GL.GL_UNSIGNED_INT),np.uint32).reshape(16,16,16,4)
        wanted=np.zeros_like(actual)
        for cells,offset in ((scene,0),(glass,2)):
            for (cx,cy,cz),value in cells:
                if offset==0 and source_table[value,0]==0:continue
                bit=(cx&3)+4*(cy&3)+16*(cz&3)
                wanted[cz//4,cy//4,cx//4,offset+bit//32]|=np.uint32(1<<(bit&31))
        check('GPU hierarchy matches occupancy: '+name,np.array_equal(actual,wanted))
        rows=np.zeros((nside*nside,2,4),np.float32)
        rows[:,0,0]=(-width+2*width*x/(nside-1)).reshape(-1)
        rows[:,0,1]=.025
        rows[:,0,2]=(-length+2*length*y/(nside-1)).reshape(-1)
        rows[:,1,:3]=[.5,2.5,.5]
        optimized=run(8,rows)[:,0,:3];old=run(9,rows)[:,0,:3]
        error=float(np.abs(optimized-old).max())
        check('Accelerated visibility matches v5 rays: '+name,error<3e-4,rays=len(rows),max_error=error)
        # Interleave modes so clocks/thermal drift do not favour the second pass.
        old_times=[];new_times=[]
        for _ in range(3):
            old_times.extend(gpu_time(9,len(rows),3));new_times.extend(gpu_time(8,len(rows),3))
        hierarchy_ms=build_time();old_ms=statistics.median(old_times);new_ms=statistics.median(new_times)
        timings.append({'scene':name,'rays':len(rows),'v5_two_traversals_ms':old_ms,'v6_combined_ms':new_ms,
                        'hierarchy_build_ms':hierarchy_ms,'v6_with_build_ms':new_ms+hierarchy_ms,
                        'speedup_including_build':old_ms/(new_ms+hierarchy_ms),'baseline_samples_ms':old_times,'optimized_samples_ms':new_times})
    baseline_pack=SHADERS.parent.parent.parent/'deliverables/Revelation-RT-v5-Realistic.zip'
    baseline_match=None
    if baseline_pack.exists():
        with zipfile.ZipFile(baseline_pack) as z:
            baseline_match=all(z.read('shaders/'+p)==(SHADERS/p).read_bytes() for p in ('lib/lighting/SceneGrid.glsl','lib/lighting/GlassGrid.glsl'))
        check('Benchmark baseline functions unchanged from shipped v5',baseline_match)
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[5])
    GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,16,np.array([1,0,0,0],np.uint32))
    GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,16,16,np.array([32.5,33.5,32.5,7],np.float32))
    volume_ray=[[[.5,.5,-4,0],[.5,.5,4,0]]]
    set_grid('rtSceneGridTex',[]);set_grid('rtGlassGridTex',[])
    open_volume=run(10,volume_ray)[0,0]
    enclosure=[((32+dx,33+dy,32+dz),stone) for dx,dy,dz in ((-1,0,0),(1,0,0),(0,-1,0),(0,1,0),(0,0,-1),(0,0,1))]
    set_grid('rtSceneGridTex',enclosure)
    closed_volume=run(10,volume_ray)[0,0]
    check('Local haze receives visible source and is blocked by enclosure',np.isfinite(open_volume).all() and open_volume[:3].max()>0 and closed_volume[:3].max()==0 and 0<open_volume[3]<=1,
          open=open_volume.tolist(),closed=closed_volume.tolist())
    set_grid('rtSceneGridTex',[])
    set_grid('rtGlassGridTex',[(cell,12) for cell,_ in enclosure])
    blue_volume=run(10,volume_ray)[0,0]
    check('Local volume scattering carries glass absorption',blue_volume[2]/blue_volume[0]>open_volume[2]/open_volume[0] and np.all(blue_volume[:3]<open_volume[:3]),result=blue_volume.tolist())
    GL.glBindBuffer(GL.GL_SHADER_STORAGE_BUFFER,buffers[5]);GL.glBufferSubData(GL.GL_SHADER_STORAGE_BUFFER,0,4,np.array([0],np.uint32))
    off_volume=run(10,volume_ray)[0,0]
    check('Local volume turns off when the source disappears',np.allclose(off_volume,[0,0,0,1]),result=off_volume.tolist())
    performance={'method':'OpenGL GL_TIME_ELAPSED; warmup; 9 interleaved samples per mode; production visibility functions',
                 'scope':'Controlled GPU visibility workload, not full Minecraft frame time or FPS','baseline_functions_match_v5':baseline_match,'scenes':timings}
    (SHADERS.parent/'validation/performance-v6.json').write_text(json.dumps(performance,indent=2)+'\n',encoding='utf-8')
    return tests,performance
