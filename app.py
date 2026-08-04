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

st.set_page_config(
    page_title="FastBuild — Proposta por Metragem de Parede",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed",
)

LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "fastbuild_logo.png")

# ----------------------------------------------------------------- Custom CSS System
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

    /* Header Banner */
    .header-container {
        display: flex;
        align-items: center;
        gap: 20px;
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        padding: 24px 32px;
        border-radius: 16px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.25);
    }
    
    .header-logo img {
        height: 64px;
        width: auto;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }

    .header-title-text {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin: 0;
        color: #ffffff;
    }

    .header-subtitle {
        font-size: 14px;
        color: #94a3b8;
        margin-top: 4px;
    }

    /* Stepper Bar */
    .stepper-container {
        display: flex;
        justify-content: space-between;
        background: #ffffff;
        padding: 16px 24px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        margin-bottom: 28px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    .step-item {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        font-weight: 600;
        color: #64748b;
    }

    .step-item.active {
        color: #0d9488;
    }

    .step-number {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #f1f5f9;
        color: #64748b;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 700;
    }

    .step-item.active .step-number {
        background: #0d9488;
        color: #ffffff;
    }

    /* Modern Card Containers */
    .custom-card {
        background: #ffffff;
        border-radius: 14px;
        padding: 24px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03);
    }

    .card-title {
        font-size: 18px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* KPI Summary Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
        margin-bottom: 24px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }

    .kpi-card-teal {
        border-left: 4px solid #0d9488;
    }
    
    .kpi-card-emerald {
        border-left: 4px solid #10b981;
    }

    .kpi-card-amber {
        border-left: 4px solid #f59e0b;
    }

    .kpi-label {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748b;
    }

    .kpi-value {
        font-size: 24px;
        font-weight: 800;
        color: #0f172a;
        margin-top: 6px;
    }

    /* Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
    }

    .badge-success {
        background-color: #dcfce7;
        color: #15803d;
    }

    .badge-warning {
        background-color: #fef3c7;
        color: #b45309;
    }

    .badge-danger {
        background-color: #fee2e2;
        color: #b91c1c;
    }

    /* Streamlit Widget Customization */
    div[data-testid="stFileUploader"] {
        background: #ffffff;
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 20px;
    }

    div[data-testid="stFileUploader"]:hover {
        border-color: #0d9488;
    }

    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    .stButton>button[kind="primary"] {
        background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
        border: none;
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.3);
    }

    .stButton>button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(13, 148, 136, 0.4);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------- Header Banner
logo_html = ""
if os.path.exists(LOGO_PATH):
    import base64
    with open(LOGO_PATH, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()
    logo_html = f'<div class="header-logo"><img src="data:image/png;base64,{encoded_string}" alt="FastBuild Logo" /></div>'

st.markdown(
    f"""
    <div class="header-container">
        {logo_html}
        <div>
            <div class="header-title-text">FastBuild Propostas</div>
            <div class="header-subtitle">Plataforma Inteligente para Medição de Paredes (DWG/DXF) & Orçamentos Automatizados</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Initialize session state variables
if "doc" not in st.session_state:
    st.session_state.doc = None
if "summary" not in st.session_state:
    st.session_state.summary = None
if "confirmed" not in st.session_state:
    st.session_state.confirmed = {}
if "included" not in st.session_state:
    st.session_state.included = {}

# Compute step indicator state
current_step = 1
if st.session_state.summary:
    current_step = 2

# Stepper Navigation
step1_active = "active" if current_step >= 1 else ""
step2_active = "active" if current_step >= 2 else ""
step3_active = "active" if current_step >= 3 else ""
step4_active = "active" if current_step >= 4 else ""

st.markdown(
    f"""
    <div class="stepper-container">
        <div class="step-item {step1_active}">
            <div class="step-number">1</div> Envio da Planta (DWG/DXF)
        </div>
        <div class="step-item {step2_active}">
            <div class="step-number">2</div> Análise de Paredes & Camadas
        </div>
        <div class="step-item {step3_active}">
            <div class="step-number">3</div> Dados do Cliente & Proposta
        </div>
        <div class="step-item {step4_active}">
            <div class="step-number">4</div> Emissão do PDF
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------- 1) Upload Section
st.markdown('<div class="card-title">📁 1. Arquivo do Projeto Arquitetônico</div>', unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Arraste ou selecione a planta baixa (.dwg ou .dxf)",
    type=["dwg", "dxf"],
    help="Arquivos DWG serão automaticamente convertidos para DXF via LibreDWG.",
)

if uploaded is not None:
    suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        src_path = tmp.name

    dxf_path = src_path
    if suffix == ".dwg":
        if not dwg2dxf_available():
            st.error(
                "O conversor DWG→DXF (LibreDWG) não está instalado ou disponível no PATH deste ambiente. "
                "Para suporte nativo a DWG, certifique-se de executar a aplicação via container Docker."
            )
            st.stop()
        with st.spinner("Convertendo arquivo DWG para DXF com LibreDWG..."):
            try:
                dxf_path = convert_dwg_to_dxf(src_path)
            except DwgConversionError as e:
                st.error(str(e))
                st.stop()

    with st.spinner("Analisando geometria vetorial e identificando camadas de parede..."):
        doc = ezdxf.readfile(dxf_path)
        summary = summarize_all_wall_layers(doc)

    st.session_state.doc = doc
    st.session_state.summary = summary
    st.session_state.dxf_path = dxf_path

    if not summary:
        st.warning(
            "Nenhuma camada contendo 'parede' no nome foi identificada automaticamente. "
            "Verifique as convenções de nomes de layers do seu arquivo CAD."
        )

# ----------------------------------------------------------------- 2) Wall Analysis & Confirmation
if st.session_state.summary:
    st.markdown('<div class="card-title" style="margin-top: 32px;">📐 2. Conferência de Metragem e Camadas Detectadas</div>', unsafe_allow_html=True)
    st.info(
        " O algoritmo separa as linhas detectadas em **Alta Confiança** (paredes com traçado duplo) "
        "e **A Revisar** (linhas simples ou hachuras). Revise os valores abaixo e ajuste a metragem final confirmada."
    )

    # Calculate overall stats
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

    # KPI Summary Cards
    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card kpi-card-teal">
                <div class="kpi-label">Total Confirmado</div>
                <div class="kpi-value">{total_confirmed:.2f} m</div>
            </div>
            <div class="kpi-card kpi-card-emerald">
                <div class="kpi-label">Alta Confiança (Duplas)</div>
                <div class="kpi-value">{total_high_conf:.2f} m</div>
            </div>
            <div class="kpi-card kpi-card-amber">
                <div class="kpi-label">A Revisar</div>
                <div class="kpi-value">{total_review:.2f} m</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Detailed Layer Expanders
    for layer_name, r in st.session_state.summary.items():
        is_rev = "REV" in layer_name.upper()
        badge_html = (
            '<span class="badge badge-danger">⚠️ Revestimento / Acabamento</span>'
            if is_rev
            else '<span class="badge badge-success">✓ Parede Estrutural</span>'
        )

        with st.expander(f"Camada: {layer_name}", expanded=True):
            st.markdown(f"Status da camada: {badge_html}", unsafe_allow_html=True)
            
            included = st.checkbox(
                "Incluir esta camada no cálculo total da proposta",
                value=st.session_state.included.get(layer_name, True),
                key=f"include_{layer_name}",
            )
            st.session_state.included[layer_name] = included

            if is_rev:
                st.caption(" O nome desta camada indica revestimento ou pintura. Desmarque caso não corresponda a paredes a instalar.")

            c1, c2 = st.columns([1.2, 1])

            with c1:
                st.write("**Detecção Automática:**")
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
                        caption="Legenda: Verde = Pares Detectados | Vermelho = Linhas A Revisar",
                        use_container_width=True,
                    )

            with c2:
                default_val = r["paired_length_m"]
                confirmed = st.number_input(
                    "Metragem CONFIRMADA (m)",
                    min_value=0.0,
                    value=float(st.session_state.confirmed.get(layer_name, default_val)),
                    step=0.5,
                    key=f"confirm_{layer_name}",
                    help="Defina o comprimento final que será considerado na proposta.",
                )
                st.session_state.confirmed[layer_name] = confirmed

# ----------------------------------------------------------------- 3) Client & Commercial Proposal
if st.session_state.summary:
    st.markdown('<div class="card-title" style="margin-top: 36px;">📝 3. Dados do Cliente e Condições Comerciais</div>', unsafe_allow_html=True)

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
        client_nome = st.text_input("Nome do cliente / empresa", value="", placeholder="Ex: Construtora Silva", key="cli_nome")
        client_doc = st.text_input("CPF / CNPJ do cliente", value="", placeholder="000.000.000-00", key="cli_doc")
        client_endereco = st.text_input("Endereço da obra", value="", placeholder="Rua da Obra, 100 - São Paulo/SP", key="cli_end")
        client_tel = st.text_input("Telefone de contato", value="", placeholder="(11) 99999-9999", key="cli_tel")
        client_email = st.text_input("E-mail do cliente", value="", placeholder="cliente@email.com", key="cli_email")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        """
        <div class="custom-card">
            <div class="card-title">💼 Condições Comerciais & Orçamento</div>
        """,
        unsafe_allow_html=True,
    )

    col_c, col_d, col_e = st.columns(3)

    with col_c:
        rate = st.number_input(
            "Valor unitário por metro (R$/m)",
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
        "Forma e condições de pagamento",
        value="50% no ato do aceite + 50% na conclusão dos serviços",
        key="comm_pag",
    )
    observacoes = st.text_area(
        "Observações adicionais ou escopo detalhado (opcional)",
        value="",
        placeholder="Ex: Não inclui frete de materiais de terceiros.",
        key="comm_obs",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ----------------------------------------------------------------- 4) Proposal PDF Generation
    st.markdown('<div class="card-title" style="margin-top: 36px;">📄 4. Geração e Emissão da Proposta</div>', unsafe_allow_html=True)

    if st.button("✨ Gerar Proposta Comercial em PDF", type="primary", use_container_width=True):
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
            st.error("Nenhuma camada de parede foi selecionada. Marque ao menos uma camada para gerar a proposta.")
            st.stop()

        budget = calculate_budget(floors, rate_per_meter=rate)

        company = Company(
            razao_social=company_razao,
            nome_fantasia=company_nome,
            cnpj=company_cnpj,
            endereco=company_endereco,
            telefone=company_tel,
            whatsapp=company_whatsapp,
            email=company_email,
        )
        client = Client(
            nome=client_nome or "Cliente",
            documento=client_doc,
            endereco_obra=client_endereco,
            telefone=client_tel,
            email=client_email,
        )
        project = Project(referencia_arquivo=uploaded.name if uploaded else "")
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
            f"🎉 Proposta gerada com sucesso! Metragem total: **{budget.total_length_m:.2f} m** | "
            f"Valor total: **{format_brl(budget.total_value)}**"
        )

        st.download_button(
            "⬇️ Baixar Proposta Comercial (PDF)",
            data=pdf_bytes,
            file_name=f"Proposta_FastBuild_{(client_nome or 'Cliente').replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
