"""Derive 1/16-block cutout occupancy from local vanilla models and alpha.

Only binary occupancy is shipped. Runtime texture packs can change the solar
shadow atlas independently; custom local models require regenerating this data.
"""
from __future__ import annotations
import io
import json
import math
from PIL import Image


def cutout_block(name):
    return name.endswith(('_trapdoor', '_door', 'copper_grate')) or name == 'iron_bars'


class AlphaGeometry:
    def __init__(self, archive):
        self.archive = archive
        self.models = {}
        self.alpha = {}

    def model(self, name):
        name = name.removeprefix('minecraft:')
        if name not in self.models:
            data = json.loads(self.archive.read('assets/minecraft/models/' + name + '.json'))
            parent = self.model(data['parent']) if data.get('parent', '').removeprefix('minecraft:').startswith('block/') else {}
            self.models[name] = {**parent, **data, 'textures': {**parent.get('textures', {}), **data.get('textures', {})}}
        return self.models[name]

    def opaque(self, face, point, textures, lo, hi):
        texture = face['texture']
        visited = set()
        while texture.startswith('#'):
            if texture in visited: raise ValueError('Texture reference cycle')
            visited.add(texture)
            texture = textures[texture[1:]]
        texture = texture.removeprefix('minecraft:')
        if texture not in self.alpha:
            self.alpha[texture] = Image.open(io.BytesIO(self.archive.read('assets/minecraft/textures/' + texture + '.png'))).convert('RGBA').getchannel('A')
        x, y, z = point
        # Java FaceBakery's face orientation, before the face's optional UV rotation.
        face_name = face['_name']
        projected = {'up': (x, z), 'down': (x, 16-z), 'north': (16-x, 16-y),
                     'south': (x, 16-y), 'west': (z, 16-y), 'east': (16-z, 16-y)}[face_name]
        default_uv = {'up': (lo[0], lo[2], hi[0], hi[2]), 'down': (lo[0], 16-hi[2], hi[0], 16-lo[2]),
                      'north': (16-hi[0], 16-hi[1], 16-lo[0], 16-lo[1]),
                      'south': (lo[0], 16-hi[1], hi[0], 16-lo[1]),
                      'west': (lo[2], 16-hi[1], hi[2], 16-lo[1]),
                      'east': (16-hi[2], 16-hi[1], 16-lo[2], 16-lo[1])}[face_name]
        u0, v0, u1, v1 = default_uv
        u = (projected[0] - u0) / max(u1-u0, 1e-6)
        v = (projected[1] - v0) / max(v1-v0, 1e-6)
        for _ in range(face.get('rotation', 0)//90): u, v = v, 1-u
        a, b, c, d = face.get('uv', default_uv)
        image = self.alpha[texture]
        px = min(image.width-1, max(0, int((a+(c-a)*u)*image.width/16)))
        py = min(image.height-1, max(0, int((b+(d-b)*v)*image.width/16)))
        return image.getpixel((px, py)) >= 128

    def voxels(self, variant):
        if isinstance(variant, list): variant = variant[0]
        model = self.model(variant['model'])
        occupied = set()
        for element in model.get('elements', []):
            if element.get('rotation', {}).get('angle', 0) != 0: continue
            lo, hi = element['from'], element['to']
            dims = [hi[a]-lo[a] for a in range(3)]
            axis = min(range(3), key=dims.__getitem__)
            thin = dims[axis] <= 4
            face_axis = {'west': 0, 'east': 0, 'down': 1, 'up': 1, 'north': 2, 'south': 2}
            # Thin elements extrude the alpha of their broad faces. Grates use
            # an alpha-tested shell; filling their AABB would seal every hole.
            for x in range(max(0, math.floor(lo[0])), min(16, math.ceil(hi[0]) if dims[0] else math.floor(lo[0])+1)):
                for y in range(max(0, math.floor(lo[1])), min(16, math.ceil(hi[1]) if dims[1] else math.floor(lo[1])+1)):
                    for z in range(max(0, math.floor(lo[2])), min(16, math.ceil(hi[2]) if dims[2] else math.floor(lo[2])+1)):
                        p = (x+.5, y+.5, z+.5)
                        solid = False
                        for name, original in element['faces'].items():
                            a = face_axis[name]
                            if thin and a != axis: continue
                            if not thin:
                                edge = hi[a] if name in ('east', 'up', 'south') else lo[a]
                                if abs(p[a]-edge) > 1.0: continue
                            face = dict(original, _name=name)
                            if self.opaque(face, p, model['textures'], lo, hi):
                                solid = True
                                break
                        if not solid: continue
                        q = [x, y, z]
                        for _ in range(int(variant.get('x', 0))//90): q[1], q[2] = 15-q[2], q[1]
                        for _ in range(int(variant.get('y', 0))//90): q[0], q[2] = 15-q[2], q[0]
                        occupied.add(tuple(q))
        return occupied

    @staticmethod
    def pack(occupied):
        words = [0] * 128
        for x, y, z in occupied:
            bit = x + 16*y + 256*z
            words[bit//32] |= 1 << (bit % 32)
        return tuple(words)
