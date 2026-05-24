#!/usr/bin/env python3
"""Reparo de malhas para impressão 3D — PyMeshLab + Trimesh."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pymeshlab
import trimesh


SUPPORTED_INPUT = {".stl", ".obj", ".ply", ".off", ".glb", ".gltf", ".3mf"}


def log(msg: str) -> None:
    print(msg, flush=True)


def load_trimesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh", process=False)
    if isinstance(mesh, trimesh.Scene):
        meshes = [g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise RuntimeError("Nenhum mesh encontrado no arquivo")
        mesh = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
    return mesh


def mesh_stats(path: Path) -> dict:
    tm = load_trimesh(path)
    ext = path.suffix.lower()
    topo = {
        "non_two_manifold_edges": -1,
        "non_two_manifold_vertices": -1,
        "boundary_edges": -1,
        "is_mesh_two_manifold": False,
    }
    if ext in {".stl", ".obj", ".ply", ".off"}:
        ms = pymeshlab.MeshSet()
        ms.load_new_mesh(str(path))
        topo = ms.get_topological_measures()
    return {
        "vertices": len(tm.vertices),
        "faces": len(tm.faces),
        "watertight": bool(tm.is_watertight),
        "euler": int(tm.euler_number),
        "non_manifold_edges": int(topo.get("non_two_manifold_edges", -1)),
        "non_manifold_vertices": int(topo.get("non_two_manifold_vertices", -1)),
        "boundary_edges": int(topo.get("boundary_edges", -1)),
        "two_manifold": bool(topo.get("is_mesh_two_manifold", False)),
    }


def apply_filter(ms: pymeshlab.MeshSet, name: str, **kwargs) -> bool:
    try:
        ms.apply_filter(name, **kwargs)
        log(f"  OK {name}")
        return True
    except Exception as exc:
        log(f"  SKIP {name}: {exc}")
        return False


def preprocess_trimesh(tm: trimesh.Trimesh) -> trimesh.Trimesh:
    """Limpeza inicial — crítica para GLB de IA (duplicatas/overlaps)."""
    log("Pré-processamento trimesh...")
    log(f"  faces brutas: {len(tm.faces):,}")

    tm.merge_vertices()
    tm.update_faces(tm.unique_faces())
    tm.update_faces(tm.nondegenerate_faces())
    tm.remove_unreferenced_vertices()

    log(f"  faces após limpeza: {len(tm.faces):,}")
    return tm


def remove_small_components(ms: pymeshlab.MeshSet) -> None:
    """Remove fragmentos soltos — usa PyMeshLab (rápido) em vez de split trimesh."""
    faces = ms.current_mesh().face_number()
    min_size = max(5000, int(faces * 0.005))
    log(f"  removendo componentes < {min_size} faces...")
    apply_filter(
        ms,
        "meshing_remove_connected_component_by_face_number",
        mincomponentsize=min_size,
        removeunref=True,
    )


def cleanup_pymeshlab(ms: pymeshlab.MeshSet) -> None:
    """Limpeza topológica antes da reconstrução watertight."""
    log("Limpeza PyMeshLab...")
    for name in (
        "meshing_remove_duplicate_vertices",
        "meshing_remove_duplicate_faces",
        "meshing_remove_unreferenced_vertices",
        "meshing_remove_null_faces",
        "meshing_remove_folded_faces",
        "meshing_remove_t_vertices",
    ):
        apply_filter(ms, name)

    apply_filter(
        ms,
        "meshing_merge_close_vertices",
        threshold=pymeshlab.PercentageValue(0.01),
    )
    remove_small_components(ms)

    for _ in range(3):
        apply_filter(ms, "meshing_repair_non_manifold_edges", method="Split Vertices")
        apply_filter(ms, "meshing_repair_non_manifold_vertices", vertdispratio=0.0)
        topo = ms.get_topological_measures()
        if topo["non_two_manifold_edges"] == 0:
            break

    apply_filter(ms, "compute_selection_by_non_manifold_edges_per_face")
    apply_filter(ms, "meshing_remove_selected_faces")
    apply_filter(ms, "meshing_repair_non_manifold_edges", method="Remove Faces")
    apply_filter(ms, "meshing_repair_non_manifold_vertices", vertdispratio=0.5)

    topo = ms.get_topological_measures()
    log(
        f"  topo: faces={ms.current_mesh().face_number():,} "
        f"nm={topo['non_two_manifold_edges']} boundary={topo['boundary_edges']}"
    )


def reconstruct_watertight(ms: pymeshlab.MeshSet, alpha: float) -> None:
    """Alpha wrap — envelope watertight que preserva forma com alpha fino."""
    log(f"Reconstrução watertight (alpha wrap {alpha}%)...")
    ms.apply_filter(
        "generate_alpha_wrap",
        alpha=pymeshlab.PercentageValue(alpha),
        offset=pymeshlab.PercentageValue(0.02),
    )
    topo = ms.get_topological_measures()
    log(
        f"  resultado: faces={ms.current_mesh().face_number():,} "
        f"nm={topo['non_two_manifold_edges']} boundary={topo['boundary_edges']} "
        f"2mf={topo['is_mesh_two_manifold']}"
    )


def refine_quality(ms: pymeshlab.MeshSet, target_faces: int | None) -> None:
    """Refino opcional: remesh leve + decimação quadric de alta qualidade."""
    faces = ms.current_mesh().face_number()
    log(f"Refino de qualidade ({faces:,} faces)...")

    # Remesh leve só se a malha for muito densa (>800k)
    if faces > 800_000:
        apply_filter(
            ms,
            "meshing_isotropic_explicit_remeshing",
            iterations=2,
            adaptive=True,
            targetlen=pymeshlab.PercentageValue(0.4),
            featuredeg=35.0,
            checksurfdist=True,
            maxsurfdist=pymeshlab.PercentageValue(0.08),
            reprojectflag=True,
        )
        faces = ms.current_mesh().face_number()
        log(f"  após remesh: {faces:,} faces")

    if target_faces and faces > target_faces:
        log(f"  decimação quadric: {faces:,} → ~{target_faces:,}")
        apply_filter(
            ms,
            "meshing_decimation_quadric_edge_collapse",
            targetfacenum=int(target_faces),
            qualitythr=0.6,
            preserveboundary=True,
            preservenormal=True,
            preservetopology=True,
            optimalplacement=True,
            planarquadric=True,
            autoclean=True,
        )
    elif faces > 1_500_000:
        target = int(faces * 0.7)
        log(f"  decimação suave: {faces:,} → ~{target:,} (70%)")
        apply_filter(
            ms,
            "meshing_decimation_quadric_edge_collapse",
            targetfacenum=target,
            qualitythr=0.6,
            preserveboundary=True,
            preservenormal=True,
            preservetopology=True,
            optimalplacement=True,
            planarquadric=True,
            autoclean=True,
        )

    apply_filter(ms, "meshing_re_orient_faces_coherently")
    apply_filter(ms, "meshing_remove_duplicate_vertices")
    apply_filter(ms, "meshing_remove_unreferenced_vertices")


def repair_print(
    input_path: Path,
    output_path: Path,
    alpha: float = 0.12,
    target_faces: int | None = None,
) -> dict:
    """Pipeline completo: GLB/STL → STL watertight para impressão."""
    log("Modo: print (PyMeshLab + Trimesh)")
    before = mesh_stats(input_path)
    log(f"Entrada: {before}")

    tm = preprocess_trimesh(load_trimesh(input_path))

    with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    tm.export(str(tmp_path))

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(tmp_path))
    cleanup_pymeshlab(ms)
    reconstruct_watertight(ms, alpha)
    refine_quality(ms, target_faces)

    ms.save_current_mesh(str(output_path), binary=True)
    tmp_path.unlink(missing_ok=True)

    after = mesh_stats(output_path)
    retained = after["faces"] / before["faces"] * 100 if before["faces"] else 0
    log(f"Retenção: {retained:.1f}% dos triângulos originais")
    log(f"Saída: {after}")
    return {
        "before": before,
        "after": after,
        "mode": "print",
        "alpha": alpha,
        "retention_pct": retained,
    }


def repair_gentle(input_path: Path, output_path: Path) -> dict:
    """Reparo leve sem reconstrução — não garante watertight."""
    log("Modo: gentle (reparo leve, sem reconstrução)")
    before = mesh_stats(input_path)
    tm = preprocess_trimesh(load_trimesh(input_path))
    tmp = output_path.with_suffix(".tmp.stl")
    tm.export(str(tmp))

    ms = pymeshlab.MeshSet()
    ms.load_new_mesh(str(tmp))
    cleanup_pymeshlab(ms)

    for size in (500, 2000, 8000, 30000, 100000):
        topo = ms.get_topological_measures()
        if topo["boundary_edges"] == 0:
            break
        if topo["non_two_manifold_edges"] == 0:
            apply_filter(
                ms,
                "meshing_close_holes",
                maxholesize=size,
                selfintersection=False,
                refinehole=True,
            )

    ms.save_current_mesh(str(output_path), binary=True)
    tmp.unlink(missing_ok=True)
    after = mesh_stats(output_path)
    return {"before": before, "after": after, "mode": "gentle"}


def default_output(input_path: Path, mode: str) -> Path:
    stem = input_path.stem
    suffix = "_print" if mode == "print" else "_repaired"
    return input_path.with_name(f"{stem}{suffix}.stl")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reparar malha para impressão 3D")
    parser.add_argument("--input", "-i", type=Path, required=True)
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument(
        "--mode",
        "-m",
        choices=["print", "gentle"],
        default="print",
        help="print = watertight via alpha wrap; gentle = reparo leve",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=0.12,
        help="Alpha wrap %% (menor = mais detalhe, padrão 0.12)",
    )
    parser.add_argument(
        "--target-faces",
        type=int,
        default=None,
        help="Limite opcional de faces na decimação quadric",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        log(f"Erro: arquivo não encontrado: {input_path}")
        return 1
    if input_path.suffix.lower() not in SUPPORTED_INPUT:
        log(f"Aviso: extensão {input_path.suffix} pode não ser suportada")

    output_path = (args.output or default_output(input_path, args.mode)).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    log(f"Entrada:  {input_path}")
    log(f"Saída:    {output_path}")
    log(f"Modo:     {args.mode}")
    if args.mode == "print":
        log(f"Alpha:    {args.alpha}%")
    log("")

    try:
        if args.mode == "print":
            result = repair_print(
                input_path,
                output_path,
                alpha=args.alpha,
                target_faces=args.target_faces,
            )
        else:
            result = repair_gentle(input_path, output_path)
    except Exception as exc:
        log(f"Erro: {exc}")
        return 1

    ok = result["after"]["watertight"] or result["after"]["two_manifold"]
    log("")
    log("Concluído!" if ok else "Concluído com avisos — verifique no fatiador.")
    log(f"Arquivo salvo: {output_path}")

    if args.json:
        print(json.dumps({"ok": ok, "output": str(output_path), **result}))

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
