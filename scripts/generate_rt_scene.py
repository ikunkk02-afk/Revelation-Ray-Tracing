"""Generate bounded, axis-aligned local ray geometry from vanilla 1.21.1 models.

Uses the locally installed Minecraft client JAR; no game code or textures are
redistributed. Rotated/non-axis-aligned elements and transparent foliage are
excluded instead of being silently inflated into full cubes.
"""
from __future__ import annotations
import argparse, itertools, json, re, zipfile, struct
from pathlib import Path
from rt_alpha_geometry import AlphaGeometry, cutout_block

ROOT = Path(__file__).resolve().parents[1]

def generate(jar: Path, material_source: Path) -> dict:
    original = material_source.read_text(encoding="utf-8")
    aliases: dict[int, list[str]] = {}
    current = None
    for line in original.splitlines():
        match = re.match(r"block\.(\d+)\s*=\s*(.*)", line)
        if match:
            current = int(match[1]); line = match[2]
        if current is None or line.lstrip().startswith("#"): continue
        aliases.setdefault(current, []).extend(t for t in line.replace("\\", " ").split() if not t.startswith("#"))
    def base_id(name, state):
        answer = 1
        for key, tokens in aliases.items():
            for token in tokens:
                parts = token.removeprefix("minecraft:").split(":")
                if parts[0] != name: continue
                if all("=" in p and state.get(p.split("=",1)[0]) in p.split("=",1)[1].split("|") for p in parts[1:]):
                    answer = max(1, key - 10000)
        return answer
    lights = {
        "torch":1,"wall_torch":1,"lantern":7,"campfire":9,"fire":1,
        "soul_torch":2,"soul_wall_torch":2,"soul_lantern":8,"soul_campfire":10,"soul_fire":2,
        "redstone_torch":3,"redstone_wall_torch":3,
        "glowstone":4,"shroomlight":4,"jack_o_lantern":4,"redstone_lamp":4,
        "sea_lantern":5,"end_rod":11,"ochre_froglight":12,"verdant_froglight":12,"pearlescent_froglight":12,
        "furnace":6,"blast_furnace":6,"smoker":6,"magma_block":6,
    }
    shapes = [()]
    classes = [(0,0,1,0)]
    alpha_shapes = [(0,) * 128]
    alpha_selectors = {}
    generated: dict[int,list[str]] = {}
    overridden = set()
    with zipfile.ZipFile(jar) as archive:
        alpha_geometry = AlphaGeometry(archive)
        cache = {}
        archive_names = set(archive.namelist())
        def elements(model):
            model = model.removeprefix("minecraft:")
            if model in cache: return cache[model]
            path = "assets/minecraft/models/" + model + ".json"
            if path not in archive_names: return []
            data = json.loads(archive.read(path))
            value = data.get("elements")
            if value is None: value = elements(data["parent"]) if "parent" in data else []
            cache[model] = value
            return value
        def model_boxes(variant):
            if isinstance(variant,list): variant = variant[0]
            boxes=[]
            for element in elements(variant["model"]):
                if element.get("rotation",{}).get("angle",0) != 0: continue
                a,b = element["from"],element["to"]
                if any(b[i]-a[i] <= 0 for i in range(3)): continue
                if any(x < 0 or x > 16 for x in a+b): continue
                points = list(itertools.product(*[(a[i],b[i]) for i in range(3)]))
                rotated=[]
                for x,y,z in points:
                    for _ in range(int(variant.get("x",0))//90): y,z = 16-z,y
                    for _ in range(int(variant.get("y",0))//90): x,z = 16-z,x
                    rotated.append((x,y,z))
                lo=tuple(round(min(p[i] for p in rotated)) for i in range(3))
                hi=tuple(round(max(p[i] for p in rotated)) for i in range(3))
                if all(hi[i] > lo[i] for i in range(3)): boxes.append(lo+hi)
            return boxes
        def condition_matches(condition,state):
            if "OR" in condition: return any(condition_matches(c,state) for c in condition["OR"])
            if "AND" in condition: return all(condition_matches(c,state) for c in condition["AND"])
            return all(state.get(k) in str(v).split("|") for k,v in condition.items())
        for path in sorted(archive.namelist()):
            if not path.startswith("assets/minecraft/blockstates/") or not path.endswith(".json"): continue
            name = Path(path).stem
            if any(s in name for s in ("glass","ice","leaves","portal")) or name in ("water","lava","light","barrier","structure_void"):
                continue
            data=json.loads(archive.read(path))
            if "variants" in data:
                variants = [(dict(p.split("=",1) for p in key.split(",") if p), model_boxes(v), alpha_geometry.voxels(v) if cutout_block(name) else None) for key,v in data["variants"].items()]
            else:
                props={}
                def gather(c):
                    for k,v in c.items():
                        if k in ("OR","AND"):
                            for item in v: gather(item)
                        else: props.setdefault(k,set()).update(str(v).split("|"))
                for part in data.get("multipart",[]): gather(part.get("when",{}))
                keys=sorted(props)
                variants=[]
                for values in itertools.product(*(sorted(props[k]) for k in keys)):
                    state=dict(zip(keys,values));boxes=[]
                    voxels=set() if cutout_block(name) else None
                    for part in data.get("multipart",[]):
                        if condition_matches(part.get("when",{}),state):
                            boxes.extend(model_boxes(part["apply"]))
                            if voxels is not None: voxels.update(alpha_geometry.voxels(part["apply"]))
                    variants.append((state,boxes,voxels))
            for state,boxes,voxels in variants:
                base=base_id(name,state)
                emitter=lights.get(name,0)
                if state.get("lit")=="false": emitter=0
                if name in lights and "lit" not in state and name in ("campfire","soul_campfire","furnace","blast_furnace","smoker","redstone_lamp","redstone_torch","redstone_wall_torch"):
                    # Properties absent from the blockstate model still affect emission.
                    variants.extend([(dict(state,lit="false"),boxes,voxels),(dict(state,lit="true"),boxes,voxels)])
                    continue
                if base == 13 or base >= 1000 or emitter in (1,2,3,7,8,9,10): boxes=[]
                boxes=tuple(sorted(set(boxes)))
                if len(boxes)>12: boxes=()
                if not boxes and not emitter and not voxels: continue
                if boxes not in shapes: shapes.append(boxes)
                shape=shapes.index(boxes)
                if voxels is not None:
                    packed_alpha=alpha_geometry.pack(voxels)
                    if packed_alpha not in alpha_shapes: alpha_shapes.append(packed_alpha)
                    shape=0x80000000 | alpha_shapes.index(packed_alpha)
                position=[.5,.5,.5]
                if name in ('torch','soul_torch','redstone_torch'): position[1]=.70
                if name.endswith('wall_torch'):
                    position[1]=.78
                    axis,sign={'north':(2,1),'south':(2,-1),'east':(0,-1),'west':(0,1)}[state['facing']]
                    position[axis]+=.22*sign
                if 'lantern' in name and name not in ('sea_lantern', 'jack_o_lantern'):
                    position[1]=.55 if state.get('hanging')=='true' else .30
                if name in ('campfire','soul_campfire'): position[1]=.45
                packed_position=sum(round(v*32)<<(6*i) for i,v in enumerate(position))
                pair=(shape,emitter,base,packed_position)
                if pair not in classes: classes.append(pair)
                scene_class=classes.index(pair)
                encoded=20000+scene_class
                assert encoded < 32768 and base < 2048
                selector="minecraft:"+name+"".join(":"+k+"="+v for k,v in sorted(state.items()))
                generated.setdefault(encoded,[]).append(selector)
                if voxels is not None: alpha_selectors[selector]=shape & 0x7fffffff
                overridden.add(name)
    lines=["# Revelation RT v3 modifications, 2026-10-26. Apache-2.0.","# Generated by scripts/generate_rt_scene.py from Minecraft 1.21.1 model bounds."]
    for key,tokens in aliases.items():
        plain=[t for t in tokens if not t.startswith("%") and t.removeprefix("minecraft:").split(":")[0] not in overridden]
        tags=[t for t in tokens if t.startswith("%")]
        if plain or tags:
            lines.append(f"block.{key} = \\")
            if tags: lines.extend(["#ifdef IRIS_TAG_SUPPORT"," ".join(tags)+" \\","#endif"])
            lines.append(" \\\n    ".join(" ".join(plain[i:i+7]) for i in range(0,len(plain),7)) if plain else "")
    for key,tokens in sorted(generated.items()):
        lines.append(f"block.{key} = \\")
        lines.append(" \\\n    ".join(" ".join(sorted(set(tokens))[i:i+5]) for i in range(0,len(set(tokens)),5)))
    (ROOT/"shaders/block.properties").write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
    descriptors=[];packed=[]
    for boxes in shapes:
        descriptors.append((len(packed),len(boxes)))
        for box in boxes: packed.append(sum(int(v)<<(5*i) for i,v in enumerate(box)))
    glsl=["// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.","// Generated vanilla model bounds, in sixteenths of a block.","#ifndef RT_SCENE_SHAPES","#define RT_SCENE_SHAPES"]
    table = classes + [(a,b,0,0) for a,b in descriptors] + [(p,0,0,0) for p in packed]
    assert len(table) <= 4096
    table += [(0,0,0,0)] * (4096-len(table))
    texture_dir=ROOT/"shaders/texture/rt"
    texture_dir.mkdir(exist_ok=True)
    (texture_dir/"scene_shapes.bin").write_bytes(b"".join(struct.pack("<4I",*row) for row in table))
    (texture_dir/"scene_alpha.bin").write_bytes(b"".join(struct.pack('<128I',*row) for row in alpha_shapes))
    (ROOT/'scripts/data/rt-alpha-selectors.json').write_text(json.dumps(alpha_selectors,indent=2)+'\n',encoding='utf-8')
    props_path=ROOT/'shaders/shaders.properties'
    props=props_path.read_text(encoding='utf-8')
    declaration=f'customTexture.rtSceneAlphaTex = texture/rt/scene_alpha.bin TEXTURE_2D RGBA32UI 32 {len(alpha_shapes)} RGBA_INTEGER UNSIGNED_INT'
    if 'customTexture.rtSceneAlphaTex' in props: props=re.sub(r'^customTexture.rtSceneAlphaTex.*$',declaration,props,flags=re.M)
    else: props=props.replace('#====# Custom Textures', declaration+'\n\n#====# Custom Textures',1)
    props_path.write_text(props,encoding='utf-8',newline='\n')
    glsl.append('#include "/lib/lighting/SceneID.glsl"')
    glsl.append("uvec2 RTSceneInfo(uint i) { return texelFetch(rtSceneShapesTex, ivec2(int(i), 0), 0).xy; }")
    glsl.append(f"uvec2 RTShapeRange(uint i) {{ return texelFetch(rtSceneShapesTex, ivec2(int(i) + {len(classes)}, 0), 0).xy; }}")
    glsl.append(f"uint RTShapeBox(uint i) {{ return texelFetch(rtSceneShapesTex, ivec2(int(i) + {len(classes)+len(shapes)}, 0), 0).r; }}")
    glsl.append("#endif")
    id_source = ["// Revelation RT v3 modifications, 2026-10-26. Apache-2.0.","#ifndef RT_SCENE_ID","#define RT_SCENE_ID",
        "uniform usampler2D rtSceneShapesTex;", f"const uint rtSceneClassCount = {len(classes)}u;",
        "uint RTSceneClass(int id) { return id > 20000 && id < 20000 + int(rtSceneClassCount) ? uint(id - 20000) : 0u; }",
        "int RTBaseBlockID(int id) { uint i = RTSceneClass(id); return i > 0u ? 10000 + int(texelFetch(rtSceneShapesTex, ivec2(int(i), 0), 0).z) : id; }", "#endif"]
    (ROOT/"shaders/lib/lighting/SceneID.glsl").write_text("\n".join(id_source)+"\n",encoding="utf-8",newline="\n")
    (ROOT/"shaders/lib/lighting/SceneShapes.glsl").write_text("\n".join(glsl)+"\n",encoding="utf-8",newline="\n")
    report={"minecraft":"1.21.1","mapped_blocks":len(overridden),"state_selectors":sum(len(set(v)) for v in generated.values()),"classes":len(classes),"shapes":len(shapes),"boxes":len(packed),"alpha_shapes":len(alpha_shapes),"alpha_state_selectors":len(alpha_selectors),"alpha_resolution":"16^3 per block","source":str(jar)}
    (ROOT/"validation/scene-models.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client",type=Path,required=True)
    parser.add_argument("--materials",type=Path,default=ROOT/"scripts/data/block-material-base.properties")
    args=parser.parse_args()
    print(json.dumps(generate(args.client,args.materials),indent=2))
