#!/usr/bin/env python3
"""
Reparo de malha STL via Blender (bmesh/bpy).

  blender --background --python blender_repair.py -- --input in.stl --output out.stl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--merge", type=float, default=0.00005)
    return parser.parse_args(argv)


def log(msg: str) -> None:
    print(msg, flush=True)


def bbox_diag(obj: bpy.types.Object) -> float:
    corners = [Vector(c) for c in obj.bound_box]
    return (corners[6] - corners[0]).length


def metrics(obj: bpy.types.Object) -> dict:
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
    m = {
        "faces": len(bm.faces),
        "nm_multi": sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "boundary": sum(1 for e in bm.edges if e.is_boundary),
    }
    if obj.mode != "EDIT":
        bm.free()
    return m


def report(obj: bpy.types.Object, label: str) -> dict:
    m = metrics(obj)
    log(f"{label}: faces={m['faces']:,} nm_multi={m['nm_multi']} boundary={m['boundary']}")
    return m


def ensure_edit(obj: bpy.types.Object) -> None:
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")


def remove_multi_face_batch(bm: bmesh.types.BMesh) -> int:
    faces = set()
    for edge in bm.edges:
        linked = list(edge.link_faces)
        if len(linked) > 2:
            faces.add(min(linked, key=lambda f: f.calc_area()))
    if not faces:
        return 0
    bmesh.ops.delete(bm, geom=list(faces), context="FACES")
    return len(faces)


def fix_multi_face(obj: bpy.types.Object) -> int:
    ensure_edit(obj)
    bm = bmesh.from_edit_mesh(obj.data)
    total = 0
    for _ in range(80):
        n = remove_multi_face_batch(bm)
        if n == 0:
            break
        total += n
    bmesh.update_edit_mesh(obj.data)
    return total


def select_boundary(obj: bpy.types.Object) -> None:
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_non_manifold(
        extend=False,
        use_wire=False,
        use_boundary=True,
        use_multi_face=False,
        use_non_contiguous=False,
        use_verts=False,
    )


def fill_holes(obj: bpy.types.Object) -> None:
    ensure_edit(obj)
    for sides in (3, 4, 5, 6, 12, 50, 200):
        select_boundary(obj)
        try:
            bpy.ops.mesh.fill_holes(sides=sides)
        except RuntimeError:
            pass


def bridge_once(obj: bpy.types.Object) -> None:
    ensure_edit(obj)
    select_boundary(obj)
    try:
        bpy.ops.mesh.edge_face_add()
    except RuntimeError:
        pass


def repair_object(obj: bpy.types.Object, merge_dist: float) -> None:
    ensure_edit(obj)
    bm = bmesh.from_edit_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    bmesh.ops.dissolve_degenerate(bm, dist=merge_dist * 0.5, edges=bm.edges)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.update_edit_mesh(obj.data)
    report(obj, "IMPORT+limpeza")

    steps = [
        ("Corrigir arestas multi-face", lambda: fix_multi_face(obj)),
        ("Fechar buracos (fill_holes)", lambda: fill_holes(obj)),
    ]

    for label, fn in steps:
        result = fn()
        after = metrics(obj)
        extra = f" (removeu {result})" if isinstance(result, int) and result else ""
        log(
            f"{label}{extra}: nm_multi={after['nm_multi']} boundary={after['boundary']} "
            f"faces={after['faces']:,}"
        )

    # Bridge limitado — fecha buracos visíveis sem loop infinito
    for i in range(6):
        m = metrics(obj)
        if m["boundary"] == 0:
            break
        log(f"Bridge {i + 1}: boundary={m['boundary']}")
        bridge_once(obj)
        fill_holes(obj)
        fix_multi_face(obj)

    fill_holes(obj)
    fix_multi_face(obj)

    ensure_edit(obj)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    report(obj, "FINAL")


def main() -> int:
    args = parse_args()
    input_path = args.input.expanduser().resolve()
    output_path = args.output.expanduser().resolve()

    if not input_path.exists():
        log(f"Erro: {input_path} não encontrado")
        return 1

    log(f"Entrada:  {input_path}")
    log(f"Saída:    {output_path}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.stl_import(filepath=str(input_path), use_mesh_validate=True)
    obj = bpy.context.selected_objects[0]

    merge_dist = max(bbox_diag(obj) * args.merge, 1e-7)
    log(f"merge dist: {merge_dist:.6f}")
    repair_object(obj, merge_dist)

    bpy.ops.object.mode_set(mode="OBJECT")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=str(output_path),
        export_selected_objects=True,
        ascii_format=False,
    )
    log(f"Salvo: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
