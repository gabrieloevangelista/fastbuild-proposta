"""
Motor de extração de metragem de parede a partir de DXF (convertido de DWG).

Estratégia:
1. Coleta todos os segmentos de reta das camadas de parede (LINE + LWPOLYLINE
   com bulge=0, tratadas segmento a segmento; ARCOS entram com o comprimento
   do arco real, sem pareamento).
2. Tenta "casar" pares de segmentos quase-paralelos e próximos (distância
   perpendicular compatível com espessura de parede) que se sobrepõem no eixo
   de direção -> isso indica as DUAS faces de uma mesma parede. O eixo
   (centerline) é reconstruído como a linha média entre as duas faces, no
   trecho onde elas se sobrepõem.
3. Segmentos que não acham par (parede desenhada em linha única, remendos,
   etc.) entram como "candidatos não pareados" - contam separado, com menor
   confiança, para revisão humana.
4. Retorna: comprimento pareado (alta confiança), comprimento não pareado
   (revisar), e a lista de segmentos de eixo para desenhar overlay de
   conferência visual.
"""
import ezdxf
import math
from dataclasses import dataclass, field

@dataclass
class Seg:
    x1: float
    y1: float
    x2: float
    y2: float
    source: str = "line"  # line | lwpolyline | arc

    @property
    def length(self):
        return math.dist((self.x1, self.y1), (self.x2, self.y2))

    @property
    def angle(self):
        # angulo em [0, pi)
        a = math.atan2(self.y2 - self.y1, self.x2 - self.x1)
        if a < 0:
            a += math.pi
        if abs(a - math.pi) < 1e-9:
            a = 0.0
        return a

    @property
    def midpoint(self):
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


def collect_segments(msp, layer_name, min_len=0.005):
    """Explode LINE/LWPOLYLINE/ARC de uma layer em segmentos de reta."""
    segs = []
    for e in msp:
        if e.dxf.layer != layer_name:
            continue
        t = e.dxftype()
        if t == "LINE":
            s = e.dxf.start
            en = e.dxf.end
            seg = Seg(s.x, s.y, en.x, en.y, "line")
            if seg.length >= min_len:
                segs.append(seg)
        elif t == "LWPOLYLINE":
            pts = list(e.get_points("xyb"))  # x, y, bulge
            n = len(pts)
            rng = range(n) if e.closed else range(n - 1)
            for i in rng:
                x1, y1, b1 = pts[i]
                x2, y2, _ = pts[(i + 1) % n]
                if abs(b1) > 1e-6:
                    # segmento com curvatura (bulge) - aproxima pelo comprimento de corda
                    # (sub-representa levemente arcos, aceitável para paredes retas)
                    seg = Seg(x1, y1, x2, y2, "lwpolyline-bulge")
                else:
                    seg = Seg(x1, y1, x2, y2, "lwpolyline")
                if seg.length >= min_len:
                    segs.append(seg)
        elif t == "ARC":
            c = e.dxf.center
            r = e.dxf.radius
            a1 = math.radians(e.dxf.start_angle)
            a2 = math.radians(e.dxf.end_angle)
            if a2 < a1:
                a2 += 2 * math.pi
            arc_len = r * (a2 - a1)
            if arc_len >= min_len:
                # guarda como segmento "reto" aproximado (corda) so' para overlay;
                # o comprimento real do arco e' guardado a parte
                x1, y1 = c.x + r * math.cos(a1), c.y + r * math.sin(a1)
                x2, y2 = c.x + r * math.cos(a2), c.y + r * math.sin(a2)
                seg = Seg(x1, y1, x2, y2, "arc")
                seg._arc_length = arc_len
                segs.append(seg)
    return segs


def project_range(seg, origin, direction):
    """Projeta os dois extremos do segmento sobre 'direction' (unitario) a partir de 'origin'."""
    def proj(px, py):
        return (px - origin[0]) * direction[0] + (py - origin[1]) * direction[1]
    t1 = proj(seg.x1, seg.y1)
    t2 = proj(seg.x2, seg.y2)
    return min(t1, t2), max(t1, t2)


def pair_wall_faces(segs, min_thickness=0.05, max_thickness=0.40,
                     angle_tol_deg=1.5, min_overlap=0.15):
    """
    Tenta parear segmentos quase-paralelos/proximos como as duas faces de uma
    parede. Retorna (centerlines, paired_ids, unpaired_segs).
    centerlines: lista de dicts {p1, p2, length, thickness, confidence}
    """
    angle_tol = math.radians(angle_tol_deg)
    n = len(segs)
    used = [False] * n
    centerlines = []

    # bucket por angulo arredondado p/ acelerar comparação
    buckets = {}
    for i, s in enumerate(segs):
        key = round(s.angle / angle_tol)
        buckets.setdefault(key, []).append(i)

    def candidates_for(i):
        s = segs[i]
        key = round(s.angle / angle_tol)
        out = []
        for k in (key - 1, key, key + 1):
            out.extend(buckets.get(k, []))
        return out

    # 1) gera TODOS os pares candidatos validos (i<j) com seu overlap
    all_pairs = []
    for i in range(n):
        si = segs[i]
        if si.length < 0.05:
            continue
        direction = (math.cos(si.angle), math.sin(si.angle))
        normal = (-direction[1], direction[0])
        origin = (si.x1, si.y1)
        for j in candidates_for(i):
            if j <= i:
                continue
            sj = segs[j]
            if sj.length < 0.05:
                continue
            if abs(sj.angle - si.angle) > angle_tol and abs(abs(sj.angle - si.angle) - math.pi) > angle_tol:
                continue
            mx, my = sj.midpoint
            rho = (mx - origin[0]) * normal[0] + (my - origin[1]) * normal[1]
            if not (min_thickness <= abs(rho) <= max_thickness):
                continue
            t1a, t1b = project_range(si, origin, direction)
            t2a, t2b = project_range(sj, origin, direction)
            overlap = max(0, min(t1b, t2b) - max(t1a, t2a))
            if overlap < min_overlap:
                continue
            all_pairs.append((overlap, i, j, direction, normal, origin, rho))

    # 2) casamento guloso GLOBAL por maior overlap primeiro (evita que um
    #    segmento "roube" o parceiro errado so por ordem de indice)
    all_pairs.sort(key=lambda t: -t[0])
    for overlap, i, j, direction, normal, origin, rho in all_pairs:
        if used[i] or used[j]:
            continue
        used[i] = True
        used[j] = True
        si, sj = segs[i], segs[j]
        t1a, t1b = project_range(si, origin, direction)
        t2a, t2b = project_range(sj, origin, direction)
        lo = max(t1a, t2a)
        hi = min(t1b, t2b)
        p1 = (origin[0] + direction[0] * lo + normal[0] * rho / 2,
              origin[1] + direction[1] * lo + normal[1] * rho / 2)
        p2 = (origin[0] + direction[0] * hi + normal[0] * rho / 2,
              origin[1] + direction[1] * hi + normal[1] * rho / 2)
        centerlines.append({
            "p1": p1, "p2": p2,
            "length": math.dist(p1, p2),
            "thickness": abs(rho),
            "confidence": "alta (parede com 2 faces detectadas)",
        })

    unpaired = [segs[i] for i in range(n) if not used[i]]
    return centerlines, unpaired


def summarize_layer(doc, layer_name, min_len=0.05):
    msp = doc.modelspace()
    segs = collect_segments(msp, layer_name)
    arcs_len = sum(getattr(s, "_arc_length", 0) for s in segs if s.source == "arc")

    straight_segs = [s for s in segs if s.source != "arc"]
    centerlines, unpaired = pair_wall_faces(straight_segs)

    paired_len = sum(c["length"] for c in centerlines)
    unpaired_len = sum(s.length for s in unpaired if s.length >= min_len)

    return {
        "layer": layer_name,
        "paired_length_m": round(paired_len, 2),
        "unpaired_length_m": round(unpaired_len, 2),
        "arc_length_m": round(arcs_len, 2),
        "num_wall_segments_detected": len(centerlines),
        "num_unpaired_candidates": len([s for s in unpaired if s.length >= min_len]),
        "centerlines": centerlines,
        "unpaired": [s for s in unpaired if s.length >= min_len],
        "total_estimate_m": round(paired_len + unpaired_len + arcs_len, 2),
    }


def detect_wall_layers(doc, keyword="parede"):
    """
    Detecta automaticamente camadas cujo nome contenha 'parede' (ou outra
    palavra-chave), pra nao depender de nomes fixos de layer que variam de
    escritorio pra escritorio.
    """
    kw = keyword.lower()
    names = set()
    for e in doc.modelspace():
        try:
            ln = e.dxf.layer
        except Exception:
            continue
        if kw in ln.lower():
            names.add(ln)
    return sorted(names)


def summarize_all_wall_layers(doc, keyword="parede"):
    """Roda summarize_layer em todas as camadas de parede detectadas."""
    layers = detect_wall_layers(doc, keyword)
    return {layer: summarize_layer(doc, layer) for layer in layers}


def render_overlay_png(doc, layer_name, output_path, title=None, dpi=140):
    """
    Gera um PNG de conferencia: geometria original em cinza, eixo de parede
    detectado (alta confianca) em verde, candidatos a revisar em vermelho.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    msp = doc.modelspace()
    segs = collect_segments(msp, layer_name)
    straight = [s for s in segs if s.source != "arc"]
    centerlines, unpaired = pair_wall_faces(straight)

    fig, ax = plt.subplots(figsize=(12, 12))
    for s in straight:
        ax.plot([s.x1, s.x2], [s.y1, s.y2], color="#dddddd", linewidth=0.6, zorder=1)
    for c in centerlines:
        p1, p2 = c["p1"], c["p2"]
        ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="#1a9850", linewidth=2.2, zorder=3)
    for s in unpaired:
        if s.length >= 0.2:
            ax.plot([s.x1, s.x2], [s.y1, s.y2], color="#d73027", linewidth=1.6, zorder=2)

    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(
        title or f"Conferência — {layer_name}\nVerde = parede detectada | Vermelho = revisar | Cinza = original",
        fontsize=10,
    )
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    import sys
    doc = ezdxf.readfile(sys.argv[1] if len(sys.argv) > 1 else "plan_out.dxf")
    layers = detect_wall_layers(doc) or [
        "0._TÉRREO_1_2 _ ARQ _ Parede",
        "1._PAVIMENTO SUPERIOR_2_2 _ ARQ _ Parede",
        "2 _ ARQ _ Parede",
    ]
    for layer in layers:
        r = summarize_layer(doc, layer)
        print(f"\n=== {layer} ===")
        print(f"  Pareado (alta confianca): {r['paired_length_m']} m  ({r['num_wall_segments_detected']} trechos)")
        print(f"  Nao pareado (revisar):    {r['unpaired_length_m']} m  ({r['num_unpaired_candidates']} trechos)")
        print(f"  Arcos:                    {r['arc_length_m']} m")
        print(f"  TOTAL estimado:           {r['total_estimate_m']} m")
