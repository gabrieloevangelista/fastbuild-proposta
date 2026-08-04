"""
FastBuild — Calculadora de Instalação por Metragem de Parede
================================================================
Fluxo:
 1. Upload do projeto arquitetônico (.dwg ou .dxf)
 2. Detecção automática das camadas de parede + cálculo (alta confiança / a revisar)
 3. Conferência visual (overlay) por pavimento — o usuário confirma/ajusta a metragem
 4. Dados do cliente e condições comerciais
 5. Geração da proposta comercial em PDF, com o valor = metros confirmados x R$/m
"""
import os
import tempfile

import streamlit as st
import ezdxf

from wall_extract import summarize_all_wall_layers, render_overlay_png
from dwg_convert import convert_dwg_to_dxf, dwg2dxf_available, DwgConversionError
from calc_engine import FloorMeasurement, calculate_budget, format_brl, DEFAULT_RATE_PER_METER
from pdf_generator import generate_proposal_pdf, Company, Client, Project, Terms

st.set_page_config(page_title="FastBuild — Proposta por Metragem de Parede", layout="wide")

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "fastbuild_logo.png")

st.markdown(
    """
    <style>
    .stApp { background-color: #fafafa; }
    </style>
    """,
    unsafe_allow_html=True,
)

col_logo, col_title = st.columns([1, 6])
with col_logo:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=90)
with col_title:
    st.title("Proposta por metragem de parede")
    st.caption("Envie a planta baixa (DWG/DXF) → confira a metragem detectada → gere a proposta em PDF")

if "doc" not in st.session_state:
    st.session_state.doc = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "confirmed" not in st.session_state:
    st.session_state.confirmed = {}

# ----------------------------------------------------------------- 1) upload
st.header("1. Projeto arquitetônico")
uploaded = st.file_uploader("Envie o arquivo da planta baixa", type=["dwg", "dxf"])

if uploaded is not None:
    suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        src_path = tmp.name

    dxf_path = src_path
    if suffix == ".dwg":
        if not dwg2dxf_available():
            st.error(
                "Conversor DWG→DXF (LibreDWG) não encontrado neste ambiente. "
                "Rode a aplicação via Docker (Dockerfile já inclui a instalação) "
                "ou suba o arquivo já em .dxf."
            )
            st.stop()
        with st.spinner("Convertendo DWG → DXF..."):
            try:
                dxf_path = convert_dwg_to_dxf(src_path)
            except DwgConversionError as e:
                st.error(str(e))
                st.stop()

    with st.spinner("Lendo geometria e detectando camadas de parede..."):
        doc = ezdxf.readfile(dxf_path)
        summary = summarize_all_wall_layers(doc)

    st.session_state.doc = doc
    st.session_state.summary = summary
    st.session_state.dxf_path = dxf_path
    if not summary:
        st.warning(
            "Nenhuma camada com 'parede' no nome foi encontrada automaticamente. "
            "Confira se o arquivo usa outra convenção de nome de camada."
        )

# --------------------------------------------------------- 2) revisão visual
if st.session_state.summary:
    st.header("2. Conferência da metragem por pavimento")
    st.info(
        "O sistema separa a metragem em **alta confiança** (parede com as duas "
        "faces detectadas) e **a revisar** (pode ser parede em linha única, ou "
        "ruído de hachura/símbolo). Confira o overlay e ajuste o valor final "
        "de cada pavimento antes de gerar a proposta."
    )

    st.caption(
        "A detecção de camada usa a palavra 'parede' no nome — isso pode "
        "pegar camadas de revestimento/acabamento (ex: 'REV _ Parede'), que "
        "não são estruturais. Desmarque as que não devem entrar no cálculo."
    )

    if "included" not in st.session_state:
        st.session_state.included = {}

    total_confirmed = 0.0
    for layer_name, r in st.session_state.summary.items():
        default_include = "REV" not in layer_name.upper() or "ARQ" in layer_name.upper()

        with st.expander(f"📐 {layer_name}", expanded=True):
            included = st.checkbox(
                "Incluir esta camada no total da proposta",
                value=st.session_state.included.get(layer_name, default_include),
                key=f"include_{layer_name}",
            )
            st.session_state.included[layer_name] = included
            if "REV" in layer_name.upper():
                st.caption("⚠️ Nome sugere camada de **revestimento/acabamento**, não parede estrutural — confirme antes de incluir.")

            c1, c2 = st.columns([1, 1])
            with c1:
                st.metric("Alta confiança", f"{r['paired_length_m']} m")
                st.metric("A revisar", f"{r['unpaired_length_m']} m")
                if r["arc_length_m"]:
                    st.metric("Arcos", f"{r['arc_length_m']} m")

                if st.button("Gerar imagem de conferência", key=f"overlay_{layer_name}"):
                    png_path = os.path.join(tempfile.gettempdir(), f"overlay_{abs(hash(layer_name))}.png")
                    render_overlay_png(st.session_state.doc, layer_name, png_path)
                    st.session_state[f"png_{layer_name}"] = png_path

                if st.session_state.get(f"png_{layer_name}"):
                    st.image(st.session_state[f"png_{layer_name}"], caption="Verde = detectado | Vermelho = revisar")

            with c2:
                default_val = r["paired_length_m"]
                confirmed = st.number_input(
                    "Metragem CONFIRMADA para a proposta (m)",
                    min_value=0.0,
                    value=float(default_val),
                    step=0.5,
                    key=f"confirm_{layer_name}",
                    help="Valor que efetivamente entra no cálculo do orçamento.",
                )
                st.session_state.confirmed[layer_name] = confirmed
                if included:
                    total_confirmed += confirmed

    st.success(f"Total confirmado até agora (camadas incluídas): **{total_confirmed:.2f} m**")

# --------------------------------------------------------------- 3) cliente
if st.session_state.summary:
    st.header("3. Dados da proposta")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Empresa (contratada)")
        company_nome = st.text_input("Nome fantasia", value="FastBuild")
        company_razao = st.text_input("Razão social", value="RFB Reformas e Construções LTDA.")
        company_cnpj = st.text_input("CNPJ", value="33.291.701/0001-86")
        company_endereco = st.text_input(
            "Endereço",
            value="Rua Rosa Gomes de Siqueira, 21 — Recanto Ana Maria, São Paulo/SP — CEP 04864-070",
        )
        company_tel = st.text_input("Telefone", value="(11) 5922-0510")
        company_whatsapp = st.text_input("WhatsApp", value="(11) 97730-8919")
        company_email = st.text_input("E-mail", value="")

    with col_b:
        st.subheader("Cliente (contratante)")
        client_nome = st.text_input("Nome do cliente", value="")
        client_doc = st.text_input("CPF/CNPJ do cliente", value="")
        client_endereco = st.text_input("Endereço da obra", value="")
        client_tel = st.text_input("Telefone do cliente", value="")
        client_email = st.text_input("E-mail do cliente", value="")

    st.subheader("Condições comerciais")
    col_c, col_d, col_e = st.columns(3)
    with col_c:
        rate = st.number_input("Valor por metro (R$)", min_value=0.0, value=DEFAULT_RATE_PER_METER, step=5.0)
    with col_d:
        validade = st.number_input("Validade da proposta (dias)", min_value=1, value=15, step=1)
    with col_e:
        prazo = st.text_input("Prazo de execução", value="A definir conforme cronograma de obra")
    pagamento = st.text_input("Forma de pagamento", value="50% no início + 50% na conclusão")
    observacoes = st.text_area("Observações adicionais (opcional)", value="")

    st.header("4. Gerar proposta")
    if st.button("📄 Gerar PDF da proposta", type="primary"):
        floors = [
            FloorMeasurement(
                name=layer_name.split("_")[-1] if "_" in layer_name else layer_name,
                confirmed_length_m=st.session_state.confirmed.get(layer_name, r["paired_length_m"]),
                auto_high_confidence_m=r["paired_length_m"],
                auto_needs_review_m=r["unpaired_length_m"],
            )
            for layer_name, r in st.session_state.summary.items()
            if st.session_state.included.get(layer_name, True)
        ]
        if not floors:
            st.error("Nenhuma camada incluída no total — marque ao menos uma camada acima.")
            st.stop()
        budget = calculate_budget(floors, rate_per_meter=rate)

        company = Company(
            razao_social=company_razao, nome_fantasia=company_nome, cnpj=company_cnpj,
            endereco=company_endereco, telefone=company_tel, whatsapp=company_whatsapp, email=company_email,
        )
        client = Client(
            nome=client_nome or "Cliente", documento=client_doc,
            endereco_obra=client_endereco, telefone=client_tel, email=client_email,
        )
        project = Project(referencia_arquivo=uploaded.name if uploaded else "")
        terms = Terms(validade_dias=int(validade), forma_pagamento=pagamento,
                      prazo_execucao=prazo, observacoes=observacoes)

        out_path = os.path.join(tempfile.gettempdir(), "proposta_fastbuild.pdf")
        generate_proposal_pdf(out_path, company, client, project, budget, terms, logo_path=LOGO_PATH)

        with open(out_path, "rb") as f:
            st.download_button(
                "⬇️ Baixar proposta em PDF",
                data=f.read(),
                file_name=f"Proposta_{(client_nome or 'cliente').replace(' ', '_')}.pdf",
                mime="application/pdf",
            )
        st.success(f"Proposta gerada: {budget.total_length_m} m × {format_brl(rate)} = {format_brl(budget.total_value)}")
