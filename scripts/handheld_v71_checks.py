"""Near-wall regression fixtures for the actual handheld producer and lighting."""
import math, json, statistics
import numpy as np
from OpenGL import GL
from validate_rt import SHADERS


def run_handheld_checks(run,set_grid,shader,stone,resolver):
    tests=[]
    def check(name,ok,**detail):
        tests.append(dict(name=name,passed=bool(ok),**detail))
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    def config(main=15,off=0,right=True):
        GL.glUseProgram(shader)
        for name,value in (('heldBlockLightValue',main),('heldBlockLightValue2',off),('heldItemId',10001),('heldItemId2',10001),('isRightHanded',right)):
            GL.glUniform1i(GL.glGetUniformLocation(shader,name),int(value))
    def rotate(matrix):
        GL.glUseProgram(shader)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(shader,'gbufferModelViewInverse'),1,GL.GL_TRUE,matrix)
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(shader,'gbufferModelView'),1,GL.GL_TRUE,np.linalg.inv(matrix))
    def positions(camera):return run(11,[[[0,0,0,0],[0,0,0,0]]],camera)[0]
    def light(point,normal,camera,old=False):
        return run(12 if old else 7,[[list(point)+[0],list(normal)+[0]]],camera)[0,0,:3]
    rotate(np.eye(4,dtype=np.float32));config();set_grid('rtGlassGridTex',[])
    sweep=[]
    for d in (.005,.01,.02,.05,.1,.2,.3,.45,.55,.59,.61,.8,1.2):
        camera=(.5,.6,d)
        set_grid('rtSceneGridTex',[((32,32,31-math.floor(d)),stone)])
        source=positions(camera)[0]
        rgb=light((0,-.05,-d),(0,0,1),camera)
        sweep.append({'distance':d,'source':source.tolist(),'rgb':rgb.tolist()})
    check('Front wall sweep: 5 mm to 1.2 m stays lit and source stays outside',
          all(np.isfinite(v['rgb']).all() and max(v['rgb'])>.001 and max(v['rgb'])<4 and v['source'][2]>-v['distance'] for v in sweep),samples=sweep)
    camera=(.5,.6,.3);set_grid('rtSceneGridTex',[((32,32,31),stone)])
    old=light((0,-.05,-.3),(0,0,1),camera,True)
    corrected=light((0,-.05,-.3),(0,0,1),camera)
    check('Reproduces v7 extinction and fixes it with the same geometry',old.max()==0 and corrected.max()>.01,v7=old.tolist(),corrected=corrected.tolist(),source=positions(camera)[0].tolist())
    hidden=light((0,-.05,-1.4),(0,0,1),camera)
    check('Full wall still blocks handheld illumination on the far side',hidden.max()==0,result=hidden.tolist())
    negative=positions((-9.5,-12.4,-3.7))[0]
    check('Negative world coordinates preserve the same near-wall position',np.allclose(negative,positions(camera)[0],atol=2e-5),source=negative.tolist())
    for right,camera,cell,point,normal in (
        (True,(.9,.6,.7),(33,32,32),(.1,-.05,-.25),(-1,0,0)),
        (False,(.1,.6,.7),(31,32,32),(-.1,-.05,-.25),(1,0,0))):
        config(right=right);set_grid('rtSceneGridTex',[(cell,stone)])
        rgb=light(point,normal,camera);previous=light(point,normal,camera,True)
        check('Side wall near '+('right' if right else 'left')+' main hand',rgb.max()>.01 and previous.max()==0,source=positions(camera)[0].tolist(),result=rgb.tolist())
    # Rotate the camera, not just the collision fixture. Lighting and resolved
    # positions must keep the same view/world convention used by actual passes.
    for name,matrix,camera,cell,normal in (
        ('yaw',np.array([[0,0,1,0],[0,1,0,0],[-1,0,0,0],[0,0,0,1]],np.float32),(.3,.6,.5),(31,32,32),(1,0,0)),
        ('pitch',np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],np.float32),(.5,.3,.5),(32,31,32),(0,1,0))):
        rotate(matrix);config();set_grid('rtSceneGridTex',[(cell,stone)])
        rgb=light((0,-.05,-.3),normal,camera);source=positions(camera)[0]
        check('Near-wall position follows '+name+' camera rotation',rgb.max()>.01 and source[2]>-.3,result=rgb.tolist(),source=source.tolist())
    rotate(np.eye(4,dtype=np.float32));set_grid('rtSceneGridTex',[]);set_grid('rtGlassGridTex',[])
    config(15,15,True);right=positions((.5,.6,.5))
    config(15,15,False);left=positions((.5,.6,.5))
    check('Both hands mirror correctly and preserve free-space offsets',np.allclose(right[:,0],[.35,-.35]) and np.allclose(left[:,0],[-.35,.35]) and np.allclose(right[:,1:3],[[-.2,-.55],[-.2,-.55]]),right=right.tolist(),left=left.tolist())
    config(0,15,True);set_grid('rtSceneGridTex',[((32,32,31),stone)])
    camera=(.5,.6,.3);off=positions(camera);rgb=light((0,-.05,-.3),(0,0,1),camera)
    check('Offhand-only emitter also survives wall contact',np.allclose(off[0],0) and off[1,2]>-.3 and rgb.max()>.01,result=rgb.tolist(),sources=off.tolist())
    config(0,0);off=positions(camera)
    check('Switching both emitters off clears both cached positions',np.allclose(off,0) and light((0,-.05,-.3),(0,0,1),camera).max()==0)
    config();set_grid('rtSceneGridTex',[])
    for code in (17,15):
        set_grid('rtGlassGridTex',[((32,32,31),code)])
        source=positions(camera)[0]
        check('Handheld proxy cannot penetrate glass code '+str(code),source[2]>-.3,source=source.tolist())
    filtered=light((0,-.05,-1.5),(0,0,1),camera)
    check('Corrected source still filters through red glass',filtered.max()>.001 and filtered[0]>filtered[1]*2,result=filtered.tolist())
    camera=(.3,.6,.5)
    set_grid('rtGlassGridTex',[((32,32,32),15|32|(5<<6))])
    pane=positions(camera)[0]
    check('Connected thin pane constrains the source at its actual plane',pane[0]<.1375,source=pane.tolist())
    set_grid('rtGlassGridTex',[((32,32,32),15|32)])
    gap=positions(camera)[0]
    check('Unconnected pane empty space does not act as a full cube',np.allclose(gap[:3],[.35,-.2,-.55],atol=2e-5),source=gap.tolist())

    # Existing independent vanilla-alpha tests establish the occupancy truth.
    # Here check the new producer's endpoint against those actual cutout shapes.
    selectors=json.loads((SHADERS.parent/'scripts/data/rt-alpha-selectors.json').read_text())
    table=np.frombuffer((SHADERS/'texture/rt/scene_shapes.bin').read_bytes(),np.uint32).reshape(-1,4)
    shapes=sorted({v for k,v in selectors.items() if k.startswith('minecraft:oak_trapdoor:') and ':open=true' in k})
    set_grid('rtGlassGridTex',[]);clipped=blocked=0;clear=True;cutout_class=None
    for shape in shapes:
        index=int(np.flatnonzero(table[:556,0]==(0x80000000|shape))[0]);cutout_class=index
        set_grid('rtSceneGridTex',[((32,32,32),index)])
        for x in (.25,.5,.75):
            cam=(x,.6,.5);source=positions(cam)[0]
            wanted=run(8,[[[0,0,0,0],[.35,-.2,-.55,0]]],cam)[0,0,:3]
            safe=run(8,[[[0,0,0,0],source.tolist()]],cam)[0,0,:3]
            clipped+=int(not np.allclose(source[:3],[.35,-.2,-.55],atol=1e-5))
            blocked+=int(wanted.max()==0);clear=clear and bool(safe.min()>.999)
    check('Actual oak trapdoor cutouts leave resolved sources on the visible side',clear and clipped>0 and blocked>0,cases=len(shapes)*3,clipped=clipped,originally_blocked=blocked)

    # Measure the extra producer once per frame, not once per receiver pixel.
    timings=[];config(15,15)
    for name,cells in [('empty',[]),('near_wall',[((32,32,31),stone)]),('cutout',[((32,32,32),cutout_class)])]:
        set_grid('rtSceneGridTex',cells);set_grid('rtGlassGridTex',[]);positions((.5,.6,.5 if name=='cutout' else .3))
        GL.glUseProgram(resolver)
        for _ in range(3):GL.glDispatchCompute(1,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS)
        query=int(np.asarray(GL.glGenQueries(1)).reshape(-1)[0]);samples=[]
        for _ in range(9):
            GL.glBeginQuery(GL.GL_TIME_ELAPSED,query);GL.glDispatchCompute(1,1,1);GL.glMemoryBarrier(GL.GL_ALL_BARRIER_BITS);GL.glEndQuery(GL.GL_TIME_ELAPSED)
            samples.append(float(GL.glGetQueryObjectuiv(query,GL.GL_QUERY_RESULT))*1e-6)
        GL.glDeleteQueries(1,[query]);timings.append({'scene':name,'median_ms':statistics.median(samples),'samples_ms':samples})
    (SHADERS.parent/'validation/handheld-position-v71-timing.json').write_text(json.dumps({'scope':'Two handheld proxies, one production dispatch per frame; not full Minecraft FPS','scenes':timings},indent=2)+'\n',encoding='utf-8')
    rotate(np.eye(4,dtype=np.float32));config(0,0);set_grid('rtSceneGridTex',[]);set_grid('rtGlassGridTex',[])
    return tests
