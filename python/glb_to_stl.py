#!/usr/bin/env python3
"""
Pipeline GLB → STL pronto para impressão 3D (Blender/bpy).

Importa o GLB gerado por IA, une meshes, limpa duplicatas e repara non-manifold.

  blender --background --python glb_to_stl.py -- \\
      --input model.glb --output model.stl
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
    parser = argparse.ArgumentParser(description="GLB → STL print-ready")
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument(
        "--merge",
        type=float,
        default=0.0001,
        help="Threshold merge como fração da diagonal do bbox",
    )
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
        "verts": len(bm.verts),
        "nm_multi": sum(1 for e in bm.edges if len(e.link_faces) > 2),
        "nm_total": sum(1 for e in bm.edges if not e.is_manifold),
        "boundary": sum(1 for e in bm.edges if e.is_boundary),
    }
    if obj.mode != "EDIT":
        bm.free()
    return m


def report(obj: bpy.types.Object, label: str) -> dict:
    m = metrics(obj)
    log(
        f"{label}: faces={m['faces']:,} verts={m['verts']:,} "
        f"nm_multi={m['nm_multi']} nm_total={m['nm_total']} boundary={m['boundary']}"
    )
    return m


def ensure_edit(obj: bpy.types.Object) -> None:
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")


def import_glb(path: Path) -> bpy.types.Object:
    ext = path.suffix.lower()
    if ext == ".glb" or ext == ".gltf":
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".stl":
        bpy.ops.wm.stl_import(filepath=str(path), use_mesh_validate=True)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise ValueError(f"Formato não suportado: {ext}")

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("Nenhum mesh encontrado no arquivo")

    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]

    if len(meshes) > 1:
        log(f"Unindo {len(meshes)} meshes...")
        bpy.ops.object.join()

    obj = bpy.context.active_object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def remove_duplicate_faces(bm: bmesh.types.BMesh) -> int:
    seen: set[tuple[int, ...]] = set()
    duplicates = []
    for face in bm.faces:
        key = tuple(sorted(v.index for v in face.verts))
        if key in seen:
            duplicates.append(face)
        else:
            seen.add(key)
    if duplicates:
        bmesh.ops.delete(bm, geom=duplicates, context="FACES")
    return len(duplicates)


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
    for _ in range(100):
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
    for sides in (3, 4, 5, 6, 8, 12, 24, 50, 100, 500):
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


def initial_cleanup(obj: bpy.types.Object, merge_dist: float) -> None:
    ensure_edit(obj)
    bm = bmesh.from_edit_mesh(obj.data)

    dup_faces = remove_duplicate_faces(bm)
    if dup_faces:
        log(f"  removeu {dup_faces} faces duplicadas")

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    bmesh.ops.dissolve_degenerate(bm, dist=merge_dist * 0.5, edges=bm.edges)

    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")

    bmesh.update_edit_mesh(obj.data)


def repair_mesh(obj: bpy.types.Object, merge_dist: float) -> None:
    report(obj, "IMPORT")
    initial_cleanup(obj, merge_dist)
    report(obj, "APÓS merge duplicatas")

    removed = fix_multi_face(obj)
    if removed:
        log(f"  removeu {removed} faces conflitantes (multi-face)")
    report(obj, "APÓS corrigir multi-face")

    fill_holes(obj)
    report(obj, "APÓS fill_holes")

    for i in range(8):
        m = metrics(obj)
        if m["boundary"] == 0 and m["nm_multi"] == 0:
            break
        log(f"Bridge {i + 1}: boundary={m['boundary']} nm_multi={m['nm_multi']}")
        bridge_once(obj)
        fill_holes(obj)
        fix_multi_face(obj)

    fill_holes(obj)
    fix_multi_face(obj)

    ensure_edit(obj)
    bm = bmesh.from_edit_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist * 0.5)
    bmesh.update_edit_mesh(obj.data)

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
    obj = import_glb(input_path)

    merge_dist = max(bbox_diag(obj) * args.merge, 1e-7)
    log(f"merge dist: {merge_dist:.6f}")

    repair_mesh(obj, merge_dist)

    final = metrics(obj)
    if final["nm_total"] > 100 or final["boundary"] > 50:
        log("")
        log("AVISO: malha ainda tem problemas significativos.")
        log("Considere usar modo watertight (alpha wrap) como fallback.")

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
