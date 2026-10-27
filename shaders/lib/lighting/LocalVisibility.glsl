// Revelation RT v6, Apache-2.0. Shared finite light segment, one traversal.
#ifndef RT_LOCAL_VISIBILITY
#define RT_LOCAL_VISIBILITY
#include "/lib/lighting/GlassMaterial.glsl"
#ifdef RT_SCENE_ENABLED
#include "/lib/lighting/SceneGrid.glsl"
#endif
#ifdef RT_GLASS_ENABLED
#include "/lib/lighting/GlassGrid.glsl"
#endif
#ifdef RT_LOCAL_ACCELERATION
uniform usampler3D rtLocalHierarchyTex;
#endif

float RTCellExit(vec3 origin,vec3 direction,vec3 invDirection,vec3 lo,vec3 hi) {
    vec3 edge=mix(lo,hi,greaterThan(direction,vec3(0.0)));
    vec3 distances=mix(vec3(1e20),(edge-origin)*invDirection,greaterThan(abs(direction),vec3(1e-7)));
    return minOf(distances);
}

vec3 RTTraceLocalVisibility(vec3 playerOrigin,vec3 playerTarget,bool traceOpaque) {
    vec3 origin=playerOrigin+fract(cameraPosition)+vec3(32.0);
    vec3 target=playerTarget+fract(cameraPosition)+vec3(32.0);
    vec3 delta=target-origin;
    float distanceToLight=length(delta);
    if(distanceToLight<0.003) return vec3(1.0);
    vec3 direction=delta/distanceToLight;
    vec3 invDirection=sign(direction)/max(abs(direction),vec3(1e-20));
    float maxDistance=max(distanceToLight-0.002,0.0);
    vec2 span=RTGlassBoxInterval(origin,direction,maxDistance,vec3(0.0),vec3(64.0));
    if(span.y<=span.x) return vec3(1.0);
    float t=span.x+1e-4;
    ivec3 finalCell=ivec3(floor(target));
    ivec3 previousBrick=ivec3(-1);
    uvec4 masks=uvec4(0xffffffffu);
    vec3 opticalDepth=vec3(0.0);
    // A segment crosses at most ceil(length * L1(direction)) grid planes.
    // Four extra steps cover the initial cell and boundary roundoff. Keeping
    // this bound dependent on the actual ray also prevents driver expansion of
    // 192 copies of the shape/glass tracer inside every light sample.
    int stepLimit=min(192,int(ceil((span.y-span.x)*dot(abs(direction),vec3(1.0))))+4);
    for(int stepIndex=0;stepIndex<stepLimit;++stepIndex) {
        if(t>=span.y) break;
        ivec3 cell=ivec3(floor(origin+direction*t));
        if(any(lessThan(cell,ivec3(0)))||any(greaterThanEqual(cell,ivec3(64)))) break;
#ifdef RT_LOCAL_ACCELERATION
        ivec3 brick=cell>>2;
        if(any(notEqual(brick,previousBrick))) {
            masks=texelFetch(rtLocalHierarchyTex,brick,0);
            previousBrick=brick;
        }
        if(all(equal(masks,uvec4(0u)))) {
            vec3 lo=vec3(brick*4);
            t=RTCellExit(origin,direction,invDirection,lo,lo+4.0)+1e-4;
            continue;
        }
        uint bit=uint((cell.x&3)+4*(cell.y&3)+16*(cell.z&3));
        int word=int(bit>>5u);uint mask=1u<<(bit&31u);
        bool hasOpaque=(masks[word]&mask)!=0u;
        bool hasGlass=(masks[word+2]&mask)!=0u;
#else
        const bool hasOpaque=true,hasGlass=true;
#endif
#ifdef RT_SCENE_ENABLED
        if(hasOpaque && traceOpaque) {
            uint index=texelFetch(rtSceneGridTex,cell,0).r;
            if(index>0u && index<rtSceneClassCount) {
                uvec2 info=RTSceneInfo(index);
                // Only the emitter's own solid cell is exempt. A trapdoor or
                // wall in the terminal cell still blocks a handheld source.
                bool emitterCell=all(equal(cell,finalCell)) && info.y!=0u;
                if(!emitterCell && info.x!=0u && RTShapeHit(info.x,origin-vec3(cell),direction,maxDistance)) return vec3(0.0);
            }
        }
#endif
#ifdef RT_GLASS_ENABLED
        if(hasGlass) {
            uint code=texelFetch(rtGlassGridTex,cell,0).r;
            if(code!=0u) {
                float lengthInGlass=RTGlassPathLength(code,origin-vec3(cell),direction,maxDistance);
                opticalDepth+=RTGlassAbsorptionCoefficient(code)*(lengthInGlass*RT_GLASS_DENSITY);
                if(minOf(opticalDepth)>6.215) return vec3(0.0);
            }
        }
#endif
        t=RTCellExit(origin,direction,invDirection,vec3(cell),vec3(cell)+1.0)+1e-4;
    }
    return exp(-opticalDepth);
}
vec3 RTTraceLocalVisibility(vec3 playerOrigin,vec3 playerTarget) { return RTTraceLocalVisibility(playerOrigin,playerTarget,true); }
#endif
