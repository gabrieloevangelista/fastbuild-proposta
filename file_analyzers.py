"""
Módulo de análise multi-formato para plantas e projetos arquitetônicos.

Suporta:
  - DWG / DXF: extrai camadas, áreas (m²) e metragem de paredes via wall_extract.
  - PDF: extrai texto e procura cotas de área (m²) via PyMuPDF (fitz).
  - IMG (PNG, JPG, JPEG, WEBP): registra imagem como referência visual.

A função `merge_analysis_results` funde todos os dados em um summary unificado.
"""
import os
import re
import tempfile
import math

import ezdxf

from wall_extract import summarize_all_wall_layers, render_overlay_png
from dwg_convert import convert_dwg_to_dxf, dwg2dxf_available, DwgConversionError


# ---------------------------------------------------------------------------
# DWG / DXF analysis
# ---------------------------------------------------------------------------

def analyze_dwg_dxf(file_path: str) -> dict:
    """
    Analisa um arquivo DWG ou DXF e retorna:
      {
        "type": "dwg",
        "doc": <ezdxf document>,
        "dxf_path": str,
        "layers": { layer_name: { area_m2, paired_length_m, ... }, ... },
        "source_file": str,
      }
    """
    suffix = os.path.splitext(file_path)[1].lower()
    dxf_path = file_path

    if suffix == ".dwg":
        if not dwg2dxf_available():
            raise DwgConversionError(
                "Conversor DWG→DXF (LibreDWG) não encontrado neste ambiente."
            )
        dxf_path = convert_dwg_to_dxf(file_path)

    doc = ezdxf.readfile(dxf_path)
    layers = summarize_all_wall_layers(doc)

    return {
        "type": "dwg",
        "doc": doc,
        "dxf_path": dxf_path,
        "layers": layers,
        "source_file": os.path.basename(file_path),
    }


# ---------------------------------------------------------------------------
# PDF analysis
# ---------------------------------------------------------------------------

_AREA_PATTERNS = [
    # "123.45 m²", "123,45m²", "123.45m2"
    re.compile(r"(\d[\d.,]*)\s*m[²2]", re.IGNORECASE),
    # "Área = 200 m²", "Área Total: 200,50 m²", "AREA CONSTRUIDA 350.00m²"
    re.compile(
        r"[áÁaA]rea\s*(?:total|constru[íi]da|coberta|privativa)?\s*[=:]\s*(\d[\d.,]*)\s*m[²2]",
        re.IGNORECASE,
    ),
    # "AT = 200.00", "AC = 150.00" (common abbreviations in Brazilian arch. plans)
    re.compile(r"\b(?:AT|AC|AP)\s*[=:]\s*(\d[\d.,]*)\s*m[²2]?", re.IGNORECASE),
]


def _parse_area_value(raw: str) -> float:
    """Converte string numérica brasileira para float: '1.234,56' -> 1234.56"""
    cleaned = raw.strip()
    if "," in cleaned and "." in cleaned:
        # 1.234,56 format
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        # 234,56 format
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def analyze_pdf(file_path: str) -> dict:
    """
    Analisa um PDF e extrai texto + áreas dimensionais encontradas.
    Retorna:
      {
        "type": "pdf",
        "pages": [
          {
            "page_num": int,
            "text": str,
            "areas_found": [float, ...],  # m² values found
            "best_area_m2": float,  # largest area found on this page
          }, ...
        ],
        "total_area_m2": float,
        "all_texts": str,
        "source_file": str,
      }
    """
    import fitz  # PyMuPDF

    doc = fitz.open(file_path)
    pages = []
    total_area = 0.0

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text") or ""

        areas_found = []
        for pattern in _AREA_PATTERNS:
            for match in pattern.finditer(text):
                val = _parse_area_value(match.group(1))
                if 1.0 <= val <= 100_000:  # plausible area range
                    areas_found.append(val)

        # Deduplicate and keep unique values
        areas_found = sorted(set(areas_found), reverse=True)
        best_area = areas_found[0] if areas_found else 0.0

        pages.append({
            "page_num": page_num + 1,
            "text": text.strip(),
            "areas_found": areas_found,
            "best_area_m2": best_area,
        })

        total_area += best_area

    doc.close()

    all_texts = "\n\n".join(
        f"--- Página {p['page_num']} ---\n{p['text']}" for p in pages if p["text"]
    )

    return {
        "type": "pdf",
        "pages": pages,
        "total_area_m2": round(total_area, 2),
        "all_texts": all_texts,
        "source_file": os.path.basename(file_path),
    }


# ---------------------------------------------------------------------------
# Image analysis
# ---------------------------------------------------------------------------

def analyze_image(file_path: str) -> dict:
    """
    Registra uma imagem como referência visual.
    Retorna:
      {
        "type": "img",
        "image_path": str,
        "width": int,
        "height": int,
        "source_file": str,
      }
    """
    from PIL import Image

    img = Image.open(file_path)
    width, height = img.size
    img.close()

    return {
        "type": "img",
        "image_path": file_path,
        "width": width,
        "height": height,
        "source_file": os.path.basename(file_path),
    }


# ---------------------------------------------------------------------------
# Merge / Fusion
# ---------------------------------------------------------------------------

def merge_analysis_results(results: list[dict]) -> dict:
    """
    Funde os resultados de múltiplos arquivos em um summary unificado.

    Retorna:
      {
        "layers": {
          "layer_name": {
            "area_m2": float,
            "paired_length_m": float,
            "unpaired_length_m": float,
            "arc_length_m": float,
            "source": str,     # "DWG" | "PDF" | "IMG"
            "source_file": str,
            ... (demais campos de wall_extract)
          },
        },
        "docs": [ezdxf docs],           # for overlay rendering
        "dxf_paths": [str],
        "images": [{ path, width, height, source_file }],
        "pdf_texts": str,
        "source_files": [str],
      }
    """
    merged_layers = {}
    docs = []
    dxf_paths = []
    images = []
    pdf_texts_parts = []
    source_files = []

    for result in results:
        source_files.append(result["source_file"])

        if result["type"] == "dwg":
            docs.append(result["doc"])
            dxf_paths.append(result["dxf_path"])
            for layer_name, layer_data in result["layers"].items():
                # Prefix layer name with source file to avoid collisions
                unique_key = f"{result['source_file']} → {layer_name}"
                merged_layers[unique_key] = {
                    **layer_data,
                    "source": "DWG",
                    "source_file": result["source_file"],
                    "original_layer": layer_name,
                    "doc_index": len(docs) - 1,
                }

        elif result["type"] == "pdf":
            if result["all_texts"]:
                pdf_texts_parts.append(
                    f"📄 {result['source_file']}:\n{result['all_texts']}"
                )
            for page_info in result["pages"]:
                if page_info["best_area_m2"] > 0:
                    page_key = f"PDF: {result['source_file']} — Pág. {page_info['page_num']}"
                    merged_layers[page_key] = {
                        "area_m2": page_info["best_area_m2"],
                        "paired_length_m": 0.0,
                        "unpaired_length_m": 0.0,
                        "arc_length_m": 0.0,
                        "num_wall_segments_detected": 0,
                        "num_unpaired_candidates": 0,
                        "centerlines": [],
                        "unpaired": [],
                        "total_estimate_m": 0.0,
                        "num_closed_shapes": 0,
                        "source": "PDF",
                        "source_file": result["source_file"],
                        "areas_found_on_page": page_info["areas_found"],
                        "page_text": page_info["text"],
                    }

        elif result["type"] == "img":
            images.append({
                "path": result["image_path"],
                "width": result["width"],
                "height": result["height"],
                "source_file": result["source_file"],
            })

    return {
        "layers": merged_layers,
        "docs": docs,
        "dxf_paths": dxf_paths,
        "images": images,
        "pdf_texts": "\n\n".join(pdf_texts_parts),
        "source_files": source_files,
    }
