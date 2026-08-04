"""
FastBuild — Calculadora de Instalação por Metragem de Parede
================================================================
"""
import os
import tempfile
import base64

import streamlit as st
import ezdxf

from wall_extract import summarize_all_wall_layers, render_overlay_png
from dwg_convert import convert_dwg_to_dxf, dwg2dxf_available, DwgConversionError
from calc_engine import FloorMeasurement, calculate_budget, format_brl, DEFAULT_RATE_PER_METER
from pdf_generator import generate_proposal_pdf, Company, Client, Project, Terms

st.set_page_config(
    page_title="FastBuild — Proposta por Metragem de Parede",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "fastbuild_logo.png")

# ----------------------------------------------------------------- Custom Light Clean CSS
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }

    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
    }

    /* Light Clean Header Banner */
    .header-container {
        display: flex;
        align-items: center;
        gap: 20px;
        background: #ffffff;
        padding: 20px 28px;
        border-radius: 16px;
        border: 1px solid #e2e8f0;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }
    
    .header-logo img {
        height: 52px;
        width: auto;
        border-radius: 10px;
    }

    .header-title-text {
        font-size: 24px;
        font-weight: 800;
        color: #0f172a;
        margin: 0;
        letter-spacing: -0.3px;
    }

    .header-subtitle {
        font-size: 13px;
        color: #64748b;
        margin-top: 2px;
    }

    /* Custom Streamlit Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #ffffff;
        padding: 6px 10px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
    }

    .stTabs [data-baseweb="tab"] {
        height: 42px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 14px;
        color: #64748b;
        padding: 0 20px;
        border: none;
    }

    .stTabs [aria-selected="true"] {
        background-color: #0d9488 !important;
        color: #ffffff !important;
    }

    /* Modern Card Containers */
    .custom-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 24px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
    }

    .card-title {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* KPI Summary Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 20px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    .kpi-card-teal { border-left: 4px solid #0d9488; }
    .kpi-card-emerald { border-left: 4px solid #10b981; }
    .kpi-card-amber { border-left: 4px solid #f59e0b; }

    .kpi-label {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748b;
    }

    .kpi-value {
        font-size: 22px;
        font-weight: 800;
        color: #0f172a;
        margin-top: 4px;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }

    .badge-success { background-color: #dcfce7; color: #15803d; }
    .badge-danger { background-color: #fee2e2; color: #b91c1c; }

    /* Buttons */
    .stButton>button[kind="primary"] {
        background: #0d9488;
        border: none;
        font-weight: 700;
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.2);
    }
    
    .stButton>button[kind="primary"]:hover {
        background: #0f766e;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------- Header Banner (Light Background)
logo_html = ""
if os.path.exists(LOGO_PATH):
    with open(LOGO_PATH, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()
    logo_html = f'<div class="header-logo"><img src="data:image/png;base64,{encoded_string}" alt="FastBuild Logo" /></div>'

st.markdown(
    f"""
    <div class="header-container">
        {logo_html}
        <div>
            <div class="header-title-text">FastBuild Propostas</div>
            <div class="header-subtitle">Medição de Paredes em Desenhos CAD (DWG/DXF) & Geração Automática de Orçamentos</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize Session State
if "doc" not in st.session_state:
    st.session_state.doc = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "confirmed" not in st.session_state:
    st.session_state.confirmed = {}
if "included" not in st.session_state:
    st.session_state.included = {}
if "processed_file_key" not in st.session_state:
    st.session_state.processed_file_key = None

# Tab Navigation
tab1, tab2, tab3 = st.tabs([
    "📁 1. Planta & Medição",
    "🏢 2. Empresa & Cliente",
    "📄 3. Condições & Gerar PDF"
])

# ----------------------------------------------------------------- Tab 1: Planta & Medição
with tab1:
    st.markdown('<div class="card-title">Upload da Planta Baixa</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Selecione o arquivo da planta (.dwg ou .dxf)",
        type=["dwg", "dxf"],
        help="Arquivos DWG são automaticamente convertidos para DXF.",
    )

    # Process upload ONLY ONCE per file (prevents constant reload on form edits)
    if uploaded is not None:
        file_key = f"{uploaded.name}_{uploaded.size}"
        if st.session_state.processed_file_key != file_key:
            suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getvalue())
                src_path = tmp.name

            dxf_path = src_path
            if suffix == ".dwg":
                if not dwg2dxf_available():
                    st.error("Conversor DWG→DXF (LibreDWG) não encontrado neste ambiente.")
                    st.stop()
                with st.spinner("Convertendo arquivo DWG para DXF..."):
                    try:
                        dxf_path = convert_dwg_to_dxf(src_path)
                    except DwgConversionError as e:
                        st.error(str(e))
                        st.stop()

            with st.spinner("Analisando camadas e medindo paredes..."):
                doc = ezdxf.readfile(dxf_path)
                summary = summarize_all_wall_layers(doc)

            st.session_state.doc = doc
            st.session_state.summary = summary
            st.session_state.dxf_path = dxf_path
            st.session_state.processed_file_key = file_key
            st.session_state.confirmed = {}
            st.session_state.included = {}

        if not st.session_state.summary:
            st.warning("Nenhuma camada com 'parede' no nome foi encontrada. Verifique o arquivo CAD.")

    if st.session_state.summary:
        st.divider()
        st.markdown('<div class="card-title">Resumo da Medição Automatizada</div>', unsafe_allow_html=True)

        total_confirmed = 0.0
        total_high_conf = 0.0
        total_review = 0.0

        for layer_name, r in st.session_state.summary.items():
            default_include = "REV" not in layer_name.upper() or "ARQ" in layer_name.upper()
            if layer_name not in st.session_state.included:
                st.session_state.included[layer_name] = default_include

            if st.session_state.included[layer_name]:
                total_high_conf += r["paired_length_m"]
                total_review += r["unpaired_length_m"]
                total_confirmed += st.session_state.confirmed.get(layer_name, r["paired_length_m"])

        # KPI Summary Grid
        st.markdown(
            f"""
            <div class="kpi-grid">
                <div class="kpi-card kpi-card-teal">
                    <div class="kpi-label">Metragem Total Confirmada</div>
                    <div class="kpi-value">{total_confirmed:.2f} m</div>
                </div>
                <div class="kpi-card kpi-card-emerald">
                    <div class="kpi-label">Alta Confiança (Duplas)</div>
                    <div class="kpi-value">{total_high_conf:.2f} m</div>
                </div>
                <div class="kpi-card kpi-card-amber">
                    <div class="kpi-label">Linhas a Revisar</div>
                    <div class="kpi-value">{total_review:.2f} m</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="card-title">Camadas de Parede Identificadas</div>', unsafe_allow_html=True)
        for layer_name, r in st.session_state.summary.items():
            is_rev = "REV" in layer_name.upper()
            badge_html = (
                '<span class="badge badge-danger">⚠️ Revestimento</span>'
                if is_rev
                else '<span class="badge badge-success">✓ Parede Estrutural</span>'
            )

            with st.expander(f"Layer: {layer_name}", expanded=True):
                st.markdown(f"Tipo: {badge_html}", unsafe_allow_html=True)
                included = st.checkbox(
                    "Incluir no cálculo da proposta",
                    value=st.session_state.included.get(layer_name, True),
                    key=f"include_{layer_name}",
                )
                st.session_state.included[layer_name] = included

                c1, c2 = st.columns([1.2, 1])
                with c1:
                    col_m1, col_m2 = st.columns(2)
                    col_m1.metric("Alta confiança", f"{r['paired_length_m']} m")
                    col_m2.metric("A revisar", f"{r['unpaired_length_m']} m")

                    if st.button("🔍 Gerar overlay de conferência", key=f"overlay_{layer_name}"):
                        png_path = os.path.join(tempfile.gettempdir(), f"overlay_{abs(hash(layer_name))}.png")
                        render_overlay_png(st.session_state.doc, layer_name, png_path)
                        st.session_state[f"png_{layer_name}"] = png_path

                    if st.session_state.get(f"png_{layer_name}"):
                        st.image(
                            st.session_state[f"png_{layer_name}"],
                            caption="Legenda: Verde = Pares | Vermelho = Linhas A Revisar",
                            use_container_width=True,
                        )

                with c2:
                    default_val = r["paired_length_m"]
                    confirmed = st.number_input(
                        "Metragem confirmada para a proposta (m)",
                        min_value=0.0,
                        value=float(st.session_state.confirmed.get(layer_name, default_val)),
                        step=0.5,
                        key=f"confirm_{layer_name}",
                    )
                    st.session_state.confirmed[layer_name] = confirmed

# ----------------------------------------------------------------- Tab 2: Empresa & Cliente
with tab2:
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(
            """
            <div class="custom-card">
                <div class="card-title">🏢 Empresa Contratada</div>
            """,
            unsafe_allow_html=True,
        )
        company_nome = st.text_input("Nome fantasia", value="FastBuild", key="comp_nome")
        company_razao = st.text_input("Razão social", value="RFB Reformas e Construções LTDA.", key="comp_razao")
        company_cnpj = st.text_input("CNPJ", value="33.291.701/0001-86", key="comp_cnpj")
        company_endereco = st.text_input(
            "Endereço da sede",
            value="Rua Rosa Gomes de Siqueira, 21 — Recanto Ana Maria, São Paulo/SP — CEP 04864-070",
            key="comp_end",
        )
        company_tel = st.text_input("Telefone", value="(11) 5922-0510", key="comp_tel")
        company_whatsapp = st.text_input("WhatsApp", value="(11) 97730-8919", key="comp_wsp")
        company_email = st.text_input("E-mail comercial", value="contato@fastbuild.com.br", key="comp_email")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(
            """
            <div class="custom-card">
                <div class="card-title">👤 Cliente Contratante</div>
            """,
            unsafe_allow_html=True,
        )
        client_nome = st.text_input("Nome do cliente", value="", placeholder="Ex: Construtora Silva", key="cli_nome")
        client_doc = st.text_input("CPF / CNPJ", value="", placeholder="000.000.000-00", key="cli_doc")
        client_endereco = st.text_input("Endereço da obra", value="", placeholder="Rua da Obra, 100 - São Paulo/SP", key="cli_end")
        client_tel = st.text_input("Telefone", value="", placeholder="(11) 99999-9999", key="cli_tel")
        client_email = st.text_input("E-mail", value="", placeholder="cliente@email.com", key="cli_email")
        st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------- Tab 3: Condições & Gerar PDF
with tab3:
    st.markdown(
        """
        <div class="custom-card">
            <div class="card-title">💼 Condições Comerciais</div>
        """,
        unsafe_allow_html=True,
    )

    col_c, col_d, col_e = st.columns(3)
    with col_c:
        rate = st.number_input(
            "Valor por metro (R$/m)",
            min_value=0.0,
            value=DEFAULT_RATE_PER_METER,
            step=5.0,
            key="comm_rate",
        )
    with col_d:
        validade = st.number_input(
            "Validade da proposta (dias)",
            min_value=1,
            value=15,
            step=1,
            key="comm_val",
        )
    with col_e:
        prazo = st.text_input(
            "Prazo estimado de execução",
            value="A definir conforme cronograma de obra",
            key="comm_prazo",
        )

    pagamento = st.text_input(
        "Forma de pagamento",
        value="50% no início + 50% na conclusão dos serviços",
        key="comm_pag",
    )
    observacoes = st.text_area(
        "Observações adicionais (opcional)",
        value="",
        placeholder="Ex: Não inclui frete de materiais de terceiros.",
        key="comm_obs",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card-title">Emissão da Proposta em PDF</div>', unsafe_allow_html=True)

    if st.button("📄 Gerar Proposta Comercial em PDF", type="primary", use_container_width=True):
        if not st.session_state.summary:
            st.error("Faça o upload de uma planta baixa na Aba 1 antes de gerar a proposta.")
            st.stop()

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
            st.error("Nenhuma camada de parede incluída no total.")
            st.stop()

        budget = calculate_budget(floors, rate_per_meter=rate)

        company = Company(
            razao_social=st.session_state.get("comp_razao", "RFB Reformas e Construções LTDA."),
            nome_fantasia=st.session_state.get("comp_nome", "FastBuild"),
            cnpj=st.session_state.get("comp_cnpj", "33.291.701/0001-86"),
            endereco=st.session_state.get("comp_end", "Rua Rosa Gomes de Siqueira, 21 — São Paulo/SP"),
            telefone=st.session_state.get("comp_tel", "(11) 5922-0510"),
            whatsapp=st.session_state.get("comp_wsp", "(11) 97730-8919"),
            email=st.session_state.get("comp_email", "contato@fastbuild.com.br"),
        )
        client = Client(
            nome=st.session_state.get("cli_nome") or "Cliente",
            documento=st.session_state.get("cli_doc", ""),
            endereco_obra=st.session_state.get("cli_end", ""),
            telefone=st.session_state.get("cli_tel", ""),
            email=st.session_state.get("cli_email", ""),
        )
        project = Project(referencia_arquivo=uploaded.name if uploaded else "Projeto Arquitetônico")
        terms = Terms(
            validade_dias=int(validade),
            forma_pagamento=pagamento,
            prazo_execucao=prazo,
            observacoes=observacoes,
        )

        out_path = os.path.join(tempfile.gettempdir(), "proposta_fastbuild.pdf")
        generate_proposal_pdf(out_path, company, client, project, budget, terms, logo_path=LOGO_PATH)

        with open(out_path, "rb") as f:
            pdf_bytes = f.read()

        st.success(
            f"🎉 Proposta gerada! Metragem: **{budget.total_length_m:.2f} m** | "
            f"Valor Total: **{format_brl(budget.total_value)}**"
        )

        st.download_button(
            "⬇️ Baixar Proposta Comercial em PDF",
            data=pdf_bytes,
            file_name=f"Proposta_FastBuild_{(st.session_state.get('cli_nome') or 'Cliente').replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
