"""
Gerador da proposta comercial em PDF (layout com a identidade da FastBuild).

Uso:
    from pdf_generator import generate_proposal_pdf, Company, Client, Project, Terms
    generate_proposal_pdf("proposta.pdf", company, client, project, budget_result, terms, logo_path="assets/fastbuild_logo.png")
"""
import datetime
from dataclasses import dataclass, field
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from calc_engine import format_brl, BudgetResult

# ---- identidade visual FastBuild (extraida do logo) ------------------------
GREEN = HexColor("#2FAE74")
GREEN_DARK = HexColor("#1F8A5A")
CHARCOAL = HexColor("#333331")
GRAY = HexColor("#6B6B69")
LIGHT_GRAY = HexColor("#F2F2F0")
LINE_GRAY = HexColor("#DADAD8")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


@dataclass
class Company:
    razao_social: str
    nome_fantasia: str
    cnpj: str
    endereco: str
    telefone: str = ""
    whatsapp: str = ""
    email: str = ""
    site: str = ""


@dataclass
class Client:
    nome: str
    documento: str = ""       # CPF ou CNPJ
    endereco_obra: str = ""
    telefone: str = ""
    email: str = ""


@dataclass
class Project:
    titulo: str = "Instalação"
    descricao: str = (
        "Serviço de instalação sobre a metragem linear de parede identificada "
        "no projeto arquitetônico fornecido, conforme levantamento técnico "
        "descrito nesta proposta."
    )
    referencia_arquivo: str = ""


@dataclass
class Terms:
    validade_dias: int = 15
    forma_pagamento: str = "A combinar"
    prazo_execucao: str = "A combinar"
    observacoes: str = ""


def _prepare_logo_for_bg(logo_path, bg_hex):
    """
    Achata a transparencia do PNG do logo sobre uma cor de fundo solida.
    Evita halo/bloco branco quando o motor de PDF nao respeita o canal alpha
    corretamente. Retorna o caminho de um PNG temporario ja achatado.
    """
    from PIL import Image
    import tempfile, os

    im = Image.open(logo_path).convert("RGBA")
    bg_rgb = tuple(int(bg_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    bg = Image.new("RGBA", im.size, bg_rgb + (255,))
    flattened = Image.alpha_composite(bg, im).convert("RGB")

    # recorta a moldura transparente ao redor pra nao sobrar espaco vazio
    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    if bbox:
        flattened = flattened.crop(bbox)

    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    flattened.save(tmp_path)
    return tmp_path


def _wrap_text(c, text, font, size, max_width):
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def generate_proposal_pdf(output_path, company: Company, client: Client,
                           project: Project, budget: BudgetResult, terms: Terms,
                           logo_path: str = None, proposal_number: str = None):
    c = canvas.Canvas(output_path, pagesize=A4)
    today = datetime.date.today().strftime("%d/%m/%Y")
    if proposal_number is None:
        proposal_number = datetime.date.today().strftime("PROP-%Y%m%d") + "-01"

    y = PAGE_H - MARGIN

    # ---------------------------------------------------------------- header
    header_h = 26 * mm
    c.setFillColor(white)
    c.rect(0, PAGE_H - header_h, PAGE_W, header_h, fill=1, stroke=0)
    c.setStrokeColor(LINE_GRAY)
    c.setLineWidth(0.6)
    c.line(0, PAGE_H - header_h, PAGE_W, PAGE_H - header_h)
    c.setFillColor(GREEN)
    c.rect(0, PAGE_H - header_h - 2.2 * mm, PAGE_W, 2.2 * mm, fill=1, stroke=0)

    if logo_path:
        try:
            from reportlab.lib.utils import ImageReader
            flat_logo_path = _prepare_logo_for_bg(logo_path, "#FFFFFF")
            img = ImageReader(flat_logo_path)
            iw, ih = img.getSize()
            logo_h = 17 * mm
            logo_w = logo_h * iw / ih
            c.drawImage(img, MARGIN, PAGE_H - header_h / 2 - logo_h / 2, width=logo_w,
                        height=logo_h)
            text_x = MARGIN + logo_w + 6 * mm
        except Exception:
            text_x = MARGIN
    else:
        text_x = MARGIN

    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(text_x, PAGE_H - header_h / 2 + 2 * mm, company.nome_fantasia.upper())
    c.setFont("Helvetica", 7.5)
    c.setFillColor(GRAY)
    c.drawString(text_x, PAGE_H - header_h / 2 - 3.5 * mm, company.razao_social)

    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(CHARCOAL)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - header_h / 2 + 1 * mm, "PROPOSTA COMERCIAL")
    c.setFont("Helvetica", 8)
    c.setFillColor(GRAY)
    c.drawRightString(PAGE_W - MARGIN, PAGE_H - header_h / 2 - 4.5 * mm,
                       f"Nº {proposal_number}   |   {today}")

    y = PAGE_H - header_h - 12 * mm

    # ---------------------------------------------------------- client block
    box_w = (PAGE_W - 2 * MARGIN - 6 * mm) / 2
    text_w = box_w - 10 * mm

    contato_contratada = " / ".join(filter(None, [
        f"Tel {company.telefone}" if company.telefone else "",
        f"WhatsApp {company.whatsapp}" if company.whatsapp else "",
        company.email,
    ]))
    contratada_lines = [
        company.nome_fantasia + (f"  |  CNPJ {company.cnpj}" if company.cnpj else ""),
        company.endereco,
        contato_contratada,
    ]
    cliente_lines = [
        client.nome + (f"  |  {client.documento}" if client.documento else ""),
        f"Obra: {client.endereco_obra}" if client.endereco_obra else "Obra: -",
        " / ".join(filter(None, [client.telefone, client.email]) ) or "-",
    ]

    def wrapped_block(lines):
        out = []
        for ln in lines:
            out.extend(_wrap_text(c, ln, "Helvetica", 8, text_w) or [""])
        return out

    contratada_wrapped = wrapped_block(contratada_lines)
    cliente_wrapped = wrapped_block(cliente_lines)
    n_lines = max(len(contratada_wrapped), len(cliente_wrapped))
    box_h = 11 * mm + n_lines * 4.2 * mm

    def info_box(x, title, wrapped_lines):
        c.setFillColor(LIGHT_GRAY)
        c.rect(x, y - box_h, box_w, box_h, fill=1, stroke=0)
        c.setFillColor(GREEN)
        c.rect(x, y - box_h, 1.4 * mm, box_h, fill=1, stroke=0)
        c.setFillColor(CHARCOAL)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x + 5 * mm, y - 6 * mm, title)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAY)
        ty = y - 11 * mm
        for ln in wrapped_lines:
            c.drawString(x + 5 * mm, ty, ln)
            ty -= 4.2 * mm

    info_box(MARGIN, "CONTRATADA", contratada_wrapped)
    info_box(MARGIN + box_w + 6 * mm, "CLIENTE", cliente_wrapped)

    y -= box_h + 10 * mm

    # ------------------------------------------------------------- escopo
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, y, project.titulo.upper())
    y -= 5.5 * mm
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRAY)
    for line in _wrap_text(c, project.descricao, "Helvetica", 8.5, PAGE_W - 2 * MARGIN):
        c.drawString(MARGIN, y, line)
        y -= 4 * mm
    if project.referencia_arquivo:
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(MARGIN, y, f"Referência: {project.referencia_arquivo}")
        y -= 4 * mm

    y -= 6 * mm

    # -------------------------------------------------------------- tabela
    table_x = MARGIN
    table_w = PAGE_W - 2 * MARGIN
    col_widths = [table_w * 0.46, table_w * 0.18, table_w * 0.18, table_w * 0.18]
    row_h = 8 * mm

    c.setFillColor(CHARCOAL)
    c.rect(table_x, y - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8.5)
    headers = ["Pavimento / Camada", "Área Total (m²)", "Valor / m²", "Subtotal"]
    cx = table_x
    aligns = ["left", "right", "right", "right"]
    for h, w, al in zip(headers, col_widths, aligns):
        if al == "left":
            c.drawString(cx + 3 * mm, y - row_h + 2.8 * mm, h)
        else:
            c.drawRightString(cx + w - 3 * mm, y - row_h + 2.8 * mm, h)
        cx += w
    y -= row_h

    c.setFont("Helvetica", 8.5)
    for i, (name, area_m2, subtotal) in enumerate(budget.as_rows()):
        c.setFillColor(white if i % 2 == 0 else LIGHT_GRAY)
        c.rect(table_x, y - row_h, table_w, row_h, fill=1, stroke=0)
        c.setFillColor(CHARCOAL)
        cx = table_x
        vals = [name, f"{area_m2:.2f} m²", format_brl(budget.rate_per_meter), format_brl(subtotal)]
        for v, w, al in zip(vals, col_widths, aligns):
            if al == "left":
                c.drawString(cx + 3 * mm, y - row_h + 2.8 * mm, v)
            else:
                c.drawRightString(cx + w - 3 * mm, y - row_h + 2.8 * mm, v)
            cx += w
        c.setStrokeColor(LINE_GRAY)
        c.setLineWidth(0.4)
        c.line(table_x, y - row_h, table_x + table_w, y - row_h)
        y -= row_h

    # linha total
    total_h = 11 * mm
    c.setFillColor(GREEN)
    c.rect(table_x, y - total_h, table_w, total_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(table_x + 3 * mm, y - total_h + 3.7 * mm,
                 f"TOTAL — {budget.total_area_m2:.2f} m² de área total  x  {format_brl(budget.rate_per_meter)}/m²")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(table_x + table_w - 3 * mm, y - total_h + 3.3 * mm,
                       format_brl(budget.total_value))
    y -= total_h + 9 * mm


    # ------------------------------------------------------- condicoes
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(MARGIN, y, "CONDIÇÕES COMERCIAIS")
    y -= 5.5 * mm
    c.setFont("Helvetica", 8.5)
    c.setFillColor(GRAY)
    cond_lines = [
        f"Validade da proposta: {terms.validade_dias} dias a partir da data de emissão.",
        f"Forma de pagamento: {terms.forma_pagamento}.",
        f"Prazo de execução: {terms.prazo_execucao}.",
    ]
    if terms.observacoes:
        cond_lines.append(f"Observações: {terms.observacoes}")
    for line in cond_lines:
        for wrapped in _wrap_text(c, line, "Helvetica", 8.5, PAGE_W - 2 * MARGIN):
            c.drawString(MARGIN, y, wrapped)
            y -= 4.3 * mm

    y -= 8 * mm

    # ------------------------------------------------------- metodologia
    c.setFillColor(CHARCOAL)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(MARGIN, y, "SOBRE O LEVANTAMENTO DE METRAGEM")
    y -= 5.5 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(GRAY)
    metodologia = (
        "A metragem de parede acima foi extraída do projeto arquitetônico "
        "(planta baixa) fornecido pelo cliente, por pavimento, e conferida "
        "visualmente antes do fechamento desta proposta para garantir precisão "
        "no valor calculado."
    )
    for line in _wrap_text(c, metodologia, "Helvetica", 8, PAGE_W - 2 * MARGIN):
        c.drawString(MARGIN, y, line)
        y -= 4 * mm

    y -= 10 * mm

    # ------------------------------------------------------------ assinaturas
    sig_w = (PAGE_W - 2 * MARGIN - 10 * mm) / 2
    c.setStrokeColor(GRAY)
    c.setLineWidth(0.6)
    c.line(MARGIN, y, MARGIN + sig_w, y)
    c.line(MARGIN + sig_w + 10 * mm, y, MARGIN + sig_w + 10 * mm + sig_w, y)
    c.setFont("Helvetica", 8)
    c.setFillColor(GRAY)
    c.drawCentredString(MARGIN + sig_w / 2, y - 4.5 * mm, f"{company.nome_fantasia} (Contratada)")
    c.drawCentredString(MARGIN + sig_w + 10 * mm + sig_w / 2, y - 4.5 * mm, f"{client.nome} (Contratante)")

    # ------------------------------------------------------------------ footer
    c.setFillColor(LINE_GRAY)
    c.rect(0, 0, PAGE_W, 12 * mm, fill=1, stroke=0)
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 7)
    footer_txt = "  |  ".join(filter(None, [
        company.nome_fantasia, company.cnpj, company.endereco,
        f"Tel {company.telefone}" if company.telefone else "",
        f"WhatsApp {company.whatsapp}" if company.whatsapp else "",
        company.email,
    ]))
    c.drawCentredString(PAGE_W / 2, 5 * mm, footer_txt)

    c.showPage()
    c.save()
    return output_path


if __name__ == "__main__":
    from calc_engine import calculate_budget, FloorMeasurement

    company = Company(
        razao_social="RFB Reformas e Construções LTDA.",
        nome_fantasia="FastBuild",
        cnpj="33.291.701/0001-86",
        endereco="Rua Rosa Gomes de Siqueira, 21 — Recanto Ana Maria, São Paulo/SP — CEP 04864-070",
        telefone="(11) 5922-0510",
        whatsapp="(11) 97730-8919",
        email="",
    )
    client = Client(
        nome="Cliente Exemplo",
        documento="",
        endereco_obra="Conforme projeto: 01 PLANTA BAIXA EP ESTUDO PRELIMINAR.dwg",
        telefone="",
    )
    project = Project(referencia_arquivo="01 PLANTA BAIXA EP ESTUDO PRELIMINAR.dwg")
    floors = [
        FloorMeasurement("Térreo", 305.03),
        FloorMeasurement("Pavimento Superior", 336.52),
        FloorMeasurement("Nível 2 / Cobertura", 30.60),
    ]
    budget = calculate_budget(floors)
    terms = Terms(validade_dias=15, forma_pagamento="50% no início + 50% na conclusão",
                  prazo_execucao="A definir conforme cronograma de obra")

    generate_proposal_pdf("proposta_exemplo.pdf", company, client, project, budget, terms,
                          logo_path="assets/fastbuild_logo.png")
    print("PDF gerado: proposta_exemplo.pdf")
