# Orça Rápido Monolítico — Calculadora de Instalação por Metragem de Parede em Painéis EPS
import os
import tempfile
import urllib.request
import json
from PIL import Image

import streamlit as st
import ezdxf

from wall_extract import summarize_all_wall_layers, render_overlay_png
from dwg_convert import convert_dwg_to_dxf, dwg2dxf_available, DwgConversionError
from calc_engine import FloorMeasurement, calculate_budget, format_brl, DEFAULT_RATE_PER_METER
from pdf_generator import generate_proposal_pdf, Company, Client, Project, Terms

# Try importing streamlit-option-menu for modern navigation
try:
    from streamlit_option_menu import option_menu
    HAS_OPTION_MENU = True
except ImportError:
    HAS_OPTION_MENU = False

st.set_page_config(
    page_title="Orça Rápido Monolítico — Medição de Paredes EPS",
    layout="wide",
    initial_sidebar_state="collapsed",
)

LOGO_SAVED_PATH = os.path.join(tempfile.gettempdir(), "custom_company_logo.png")

# ----------------------------------------------------------------- Clean Custom CSS
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

    /* Primary Button Customization */
    .stButton>button[kind="primary"] {
        background: #0d9488;
        border: none;
        font-weight: 700;
        box-shadow: 0 2px 8px rgba(13, 148, 136, 0.2);
        border-radius: 8px;
    }
    
    .stButton>button[kind="primary"]:hover {
        background: #0f766e;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------- CNPJ Auto-Complete Helper
def fetch_cnpj_data(cnpj: str) -> dict:
    clean_cnpj = "".join(filter(str.isdigit, str(cnpj)))
    if len(clean_cnpj) != 14:
        return {}
    
    url = f"https://brasilapi.com.br/api/cnpj/v1/{clean_cnpj}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                logradouro = data.get("logradouro", "")
                numero = data.get("numero", "")
                bairro = data.get("bairro", "")
                municipio = data.get("municipio", "")
                uf = data.get("uf", "")
                cep = data.get("cep", "")
                
                end_parts = []
                if logradouro:
                    end_parts.append(f"{logradouro}, {numero}".strip(", "))
                if bairro:
                    end_parts.append(bairro)
                if municipio and uf:
                    end_parts.append(f"{municipio}/{uf}")
                if cep:
                    end_parts.append(f"CEP {cep}")
                    
                full_address = " — ".join(end_parts)
                
                return {
                    "razao_social": data.get("razao_social") or "",
                    "nome_fantasia": data.get("nome_fantasia") or data.get("razao_social") or "",
                    "cnpj": clean_cnpj,
                    "endereco": full_address,
                    "telefone": data.get("ddd_telefone_1") or "",
                    "email": data.get("email") or "",
                }
    except Exception:
        pass
    return {}

# ----------------------------------------------------------------- Saved State & Settings Persistence
if "saved_logo_path" not in st.session_state:
    if os.path.exists(LOGO_SAVED_PATH):
        st.session_state.saved_logo_path = LOGO_SAVED_PATH
    else:
        st.session_state.saved_logo_path = None

if "default_company" not in st.session_state:
    st.session_state.default_company = {
        "nome": "",
        "razao": "",
        "cnpj": "",
        "end": "",
        "tel": "",
        "wsp": "",
        "email": "",
    }

# ----------------------------------------------------------------- Native Streamlit Top Header
def _is_valid_image(path: str) -> bool:
    """Return True only if the image file exists and can be fully opened by PIL."""
    try:
        from PIL import Image as _Image
        img = _Image.open(path)
        img.verify()  # Raises if file is truncated or corrupt
        return True
    except Exception:
        return False

with st.container():
    c_logo, c_title = st.columns([1, 8])
    with c_logo:
        logo_path = st.session_state.get("saved_logo_path")
        if logo_path and os.path.exists(logo_path):
            if _is_valid_image(logo_path):
                st.image(logo_path, width=70)
            else:
                # File is truncated / corrupt — clear it so it doesn't keep crashing
                st.session_state.saved_logo_path = None
    with c_title:
        display_title = st.session_state.default_company.get("nome") or "Orça Rápido Monolítico"
        st.title(f"📐 {display_title}")
        st.caption("Medição Vetorial de Paredes em Painéis EPS & Orçamentos Automatizados")

st.divider()

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

# Pre-fill company inputs from default_company settings if not present
for comp_key, state_key in [
    ("nome", "comp_nome"),
    ("razao", "comp_razao"),
    ("cnpj", "comp_cnpj"),
    ("end", "comp_end"),
    ("tel", "comp_tel"),
    ("wsp", "comp_wsp"),
    ("email", "comp_email"),
]:
    if state_key not in st.session_state or not st.session_state[state_key]:
        st.session_state[state_key] = st.session_state.default_company.get(comp_key, "")

# Client default values in session state
for cli_field in ["cli_nome", "cli_doc", "cli_end", "cli_tel", "cli_email"]:
    if cli_field not in st.session_state:
        st.session_state[cli_field] = ""

# Navigation Menu
if HAS_OPTION_MENU:
    selected_tab = option_menu(
        menu_title=None,
        options=["Planta & Medição", "Empresa & Cliente", "Condições & Gerar PDF", "Configurações"],
        icons=["file-earmark-code", "building-gear", "file-earmark-pdf", "gear"],
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "4px", "background-color": "#ffffff", "border-radius": "10px", "border": "1px solid #e2e8f0", "margin-bottom": "20px"},
            "icon": {"color": "#0d9488", "font-size": "15px"},
            "nav-link": {"font-size": "13px", "text-align": "center", "margin": "0px 4px", "font-weight": "600", "color": "#64748b", "border-radius": "6px"},
            "nav-link-selected": {"background-color": "#0d9488", "color": "#ffffff"},
        }
    )
    tab1_active = (selected_tab == "Planta & Medição")
    tab2_active = (selected_tab == "Empresa & Cliente")
    tab3_active = (selected_tab == "Condições & Gerar PDF")
    tab4_active = (selected_tab == "Configurações")
else:
    tab1, tab2, tab3, tab4 = st.tabs([
        "📁 Planta & Medição",
        "🏢 Empresa & Cliente",
        "💼 Condições & Gerar PDF",
        "⚙️ Configurações"
    ])
    tab1_active, tab2_active, tab3_active, tab4_active = True, True, True, True

# ----------------------------------------------------------------- Tab 1: Planta & Medição
def render_tab1():
    st.subheader("📁 Upload da Planta Baixa (DWG / DXF)")
    uploaded = st.file_uploader(
        "Selecione o arquivo da planta (.dwg ou .dxf)",
        type=["dwg", "dxf"],
        help="Arquivos DWG são convertidos automaticamente para DXF via LibreDWG.",
    )

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
            st.warning("Nenhuma camada contendo 'parede' no nome foi encontrada. Verifique as camadas do arquivo CAD.")

    if st.session_state.summary:
        st.divider()
        st.subheader("📊 Resumo da Medição Automatizada")

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

        # KPI Summary Native Columns
        k1, k2, k3 = st.columns(3)
        k1.metric("Metragem Total Confirmada", f"{total_confirmed:.2f} m")
        k2.metric("Alta Confiança (Duplas)", f"{total_high_conf:.2f} m")
        k3.metric("Linhas a Revisar", f"{total_review:.2f} m")

        st.divider()
        st.subheader("🧱 Camadas de Parede Identificadas")
        for layer_name, r in st.session_state.summary.items():
            is_rev = "REV" in layer_name.upper()
            badge_label = "⚠️ Revestimento" if is_rev else "✓ Parede Estrutural"

            with st.expander(f"Layer: {layer_name} ({badge_label})", expanded=True):
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
def render_tab2():
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("🏢 Empresa Contratada (Remetente)")
        
        comp_cnpj_in = st.text_input("CNPJ da Empresa", value=st.session_state.get("comp_cnpj", ""), placeholder="00.000.000/0001-00", key="input_comp_cnpj")
        
        if st.button("🔍 Autopreencher por CNPJ (Empresa)", key="btn_cnpj_comp"):
            if comp_cnpj_in:
                with st.spinner("Consultando dados da empresa via Receita..."):
                    fetched = fetch_cnpj_data(comp_cnpj_in)
                    if fetched:
                        st.session_state["comp_razao"] = fetched["razao_social"]
                        st.session_state["comp_nome"] = fetched["nome_fantasia"]
                        st.session_state["comp_cnpj"] = fetched["cnpj"]
                        st.session_state["comp_end"] = fetched["endereco"]
                        st.session_state["comp_tel"] = fetched["telefone"]
                        st.session_state["comp_email"] = fetched["email"]
                        st.success("Dados da empresa carregados com sucesso!")
                        st.rerun()
                    else:
                        st.error("Não foi possível consultar os dados para o CNPJ informado.")

        company_nome = st.text_input("Nome fantasia / Marca", value=st.session_state.get("comp_nome", ""), placeholder="Ex: Monolítico Soluções", key="comp_nome")
        company_razao = st.text_input("Razão social", value=st.session_state.get("comp_razao", ""), placeholder="Ex: Monolítico Construções LTDA", key="comp_razao")
        company_cnpj = st.text_input("CNPJ confirmado", value=st.session_state.get("comp_cnpj", comp_cnpj_in), key="comp_cnpj")
        company_endereco = st.text_input("Endereço da sede", value=st.session_state.get("comp_end", ""), placeholder="Rua, Número, Bairro - Cidade/UF", key="comp_end")
        company_tel = st.text_input("Telefone", value=st.session_state.get("comp_tel", ""), placeholder="(11) 0000-0000", key="comp_tel")
        company_whatsapp = st.text_input("WhatsApp", value=st.session_state.get("comp_wsp", ""), placeholder="(11) 90000-0000", key="comp_wsp")
        company_email = st.text_input("E-mail comercial", value=st.session_state.get("comp_email", ""), placeholder="contato@empresa.com.br", key="comp_email")

    with col_b:
        st.subheader("👤 Cliente Contratante")
        
        cli_doc_in = st.text_input("CPF / CNPJ do Cliente", value=st.session_state.get("cli_doc", ""), placeholder="00.000.000/0001-00", key="input_cli_doc")
        
        if st.button("🔍 Autopreencher por CNPJ (Cliente)", key="btn_cnpj_cli"):
            if cli_doc_in:
                with st.spinner("Consultando dados do cliente..."):
                    fetched = fetch_cnpj_data(cli_doc_in)
                    if fetched:
                        st.session_state["cli_nome"] = fetched["nome_fantasia"] or fetched["razao_social"]
                        st.session_state["cli_doc"] = fetched["cnpj"]
                        st.session_state["cli_end"] = fetched["endereco"]
                        st.session_state["cli_tel"] = fetched["telefone"]
                        st.session_state["cli_email"] = fetched["email"]
                        st.success("Dados do cliente carregados com sucesso!")
                        st.rerun()
                    else:
                        st.error("Não foi possível consultar os dados para o CNPJ informado.")

        client_nome = st.text_input("Nome do cliente / empresa", value=st.session_state.get("cli_nome", ""), placeholder="Ex: Construtora Silva", key="cli_nome")
        client_doc = st.text_input("CPF / CNPJ confirmado", value=st.session_state.get("cli_doc", cli_doc_in), key="cli_doc")
        client_endereco = st.text_input("Endereço da obra", value=st.session_state.get("cli_end", ""), placeholder="Rua da Obra, 100 - São Paulo/SP", key="cli_end")
        client_tel = st.text_input("Telefone", value=st.session_state.get("cli_tel", ""), placeholder="(11) 99999-9999", key="cli_tel")
        client_email = st.text_input("E-mail", value=st.session_state.get("cli_email", ""), placeholder="cliente@email.com", key="cli_email")

# ----------------------------------------------------------------- Tab 3: Condições & Gerar PDF
def render_tab3():
    st.subheader("💼 Condições Comerciais")

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
        placeholder="Ex: Instalação de painéis monolíticos EPS conforme especificações técnicas do fabricante.",
        key="comm_obs",
    )

    st.divider()
    st.subheader("📄 Emissão da Proposta em PDF")

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

        comp_nome_val = st.session_state.get("comp_nome") or "Orça Rápido Monolítico"
        company = Company(
            razao_social=st.session_state.get("comp_razao") or comp_nome_val,
            nome_fantasia=comp_nome_val,
            cnpj=st.session_state.get("comp_cnpj", ""),
            endereco=st.session_state.get("comp_end", ""),
            telefone=st.session_state.get("comp_tel", ""),
            whatsapp=st.session_state.get("comp_wsp", ""),
            email=st.session_state.get("comp_email", ""),
        )
        client = Client(
            nome=st.session_state.get("cli_nome") or "Cliente",
            documento=st.session_state.get("cli_doc", ""),
            endereco_obra=st.session_state.get("cli_end", ""),
            telefone=st.session_state.get("cli_tel", ""),
            email=st.session_state.get("cli_email", ""),
        )
        uploaded_name = st.session_state.get("processed_file_key", "Projeto Arquitetônico").split("_")[0]
        project = Project(
            titulo="Instalação de Painéis Monolíticos (EPS)",
            descricao=(
                "Serviço de instalação sobre a metragem linear de parede em painel monolítico (EPS) "
                "identificada no projeto arquitetônico fornecido, conforme levantamento técnico descrito nesta proposta."
            ),
            referencia_arquivo=uploaded_name
        )
        terms = Terms(
            validade_dias=int(validade),
            forma_pagamento=pagamento,
            prazo_execucao=prazo,
            observacoes=observacoes,
        )

        logo_path_pdf = st.session_state.get("saved_logo_path")
        if logo_path_pdf and not os.path.exists(logo_path_pdf):
            logo_path_pdf = None

        out_path = os.path.join(tempfile.gettempdir(), "proposta_orcadamonolitico.pdf")
        generate_proposal_pdf(out_path, company, client, project, budget, terms, logo_path=logo_path_pdf)

        with open(out_path, "rb") as f:
            pdf_bytes = f.read()

        st.success(
            f"🎉 Proposta gerada com sucesso! Metragem: **{budget.total_length_m:.2f} m** | "
            f"Valor Total: **{format_brl(budget.total_value)}**"
        )

        cli_filename = (st.session_state.get('cli_nome') or 'Cliente').replace(' ', '_')
        st.download_button(
            "⬇️ Baixar Proposta Comercial em PDF",
            data=pdf_bytes,
            file_name=f"Proposta_Monolitico_{cli_filename}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# ----------------------------------------------------------------- Tab 4: Configurações (Logo & Dados Padrão)
def render_tab4():
    st.subheader("⚙️ Configurações da Empresa & Logotipo Padrão")
    st.caption("Cadastre o logotipo e os dados padrão da sua empresa. As informações salvas serão pré-carregadas em todas as propostas.")

    col_logo1, col_logo2 = st.columns([1, 2])
    with col_logo1:
        st.write("**Logotipo Atual:**")
        if st.session_state.get("saved_logo_path") and os.path.exists(st.session_state.saved_logo_path):
            st.image(st.session_state.saved_logo_path, width=160, caption="Logotipo Ativo para PDF")
            if st.button("❌ Remover Logotipo", key="btn_remove_logo"):
                if os.path.exists(st.session_state.saved_logo_path):
                    os.remove(st.session_state.saved_logo_path)
                st.session_state.saved_logo_path = None
                st.success("Logotipo removido com sucesso!")
                st.rerun()
        else:
            st.info("Nenhum logotipo cadastrado no momento. O cabeçalho dos PDFs utilizará o formato de texto.")

    with col_logo2:
        uploaded_logo = st.file_uploader(
            "Upload do Logotipo da Empresa (.png, .jpg, .jpeg, .webp)",
            type=["png", "jpg", "jpeg", "webp"],
            key="logo_uploader",
        )
        if uploaded_logo is not None:
            try:
                img = Image.open(uploaded_logo)
                img.save(LOGO_SAVED_PATH)
                st.session_state.saved_logo_path = LOGO_SAVED_PATH
                st.success("Logotipo salvo com sucesso! Ele será exibido em todas as propostas geradas.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar a imagem do logotipo: {e}")

    st.divider()
    st.subheader("🏢 Dados Padrão da Empresa (Remetente)")

    cnpj_def_in = st.text_input(
        "CNPJ da Empresa",
        value=st.session_state.default_company.get("cnpj", ""),
        placeholder="00.000.000/0001-00",
        key="set_cnpj_in",
    )

    if st.button("🔍 Autopreencher Dados Padrão por CNPJ", key="btn_set_cnpj"):
        if cnpj_def_in:
            with st.spinner("Consultando dados da empresa via Receita..."):
                fetched = fetch_cnpj_data(cnpj_def_in)
                if fetched:
                    st.session_state.default_company["razao"] = fetched["razao_social"]
                    st.session_state.default_company["nome"] = fetched["nome_fantasia"]
                    st.session_state.default_company["cnpj"] = fetched["cnpj"]
                    st.session_state.default_company["end"] = fetched["endereco"]
                    st.session_state.default_company["tel"] = fetched["telefone"]
                    st.session_state.default_company["email"] = fetched["email"]
                    
                    # Also sync active company session values
                    for k, v in [("nome", "comp_nome"), ("razao", "comp_razao"), ("cnpj", "comp_cnpj"), ("end", "comp_end"), ("tel", "comp_tel"), ("email", "comp_email")]:
                        st.session_state[v] = st.session_state.default_company[k]
                    
                    st.success("Dados padrão da empresa carregados por CNPJ!")
                    st.rerun()
                else:
                    st.error("Não foi possível consultar o CNPJ.")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        def_nome = st.text_input("Nome Fantasia / Marca", value=st.session_state.default_company.get("nome", ""), key="set_nome")
        def_razao = st.text_input("Razão Social", value=st.session_state.default_company.get("razao", ""), key="set_razao")
        def_cnpj = st.text_input("CNPJ", value=st.session_state.default_company.get("cnpj", cnpj_def_in), key="set_cnpj")
        def_end = st.text_input("Endereço da Sede", value=st.session_state.default_company.get("end", ""), key="set_end")
    with col_s2:
        def_tel = st.text_input("Telefone", value=st.session_state.default_company.get("tel", ""), key="set_tel")
        def_wsp = st.text_input("WhatsApp", value=st.session_state.default_company.get("wsp", ""), key="set_wsp")
        def_email = st.text_input("E-mail Comercial", value=st.session_state.default_company.get("email", ""), key="set_email")

    if st.button("💾 Salvar Configurações Padrão da Empresa", type="primary", use_container_width=True):
        st.session_state.default_company = {
            "nome": def_nome,
            "razao": def_razao,
            "cnpj": def_cnpj,
            "end": def_end,
            "tel": def_tel,
            "wsp": def_wsp,
            "email": def_email,
        }
        # Update active fields as well
        st.session_state["comp_nome"] = def_nome
        st.session_state["comp_razao"] = def_razao
        st.session_state["comp_cnpj"] = def_cnpj
        st.session_state["comp_end"] = def_end
        st.session_state["comp_tel"] = def_tel
        st.session_state["comp_wsp"] = def_wsp
        st.session_state["comp_email"] = def_email

        st.success("🎉 Configurações salvas com sucesso! Os dados padrão serão carregados em todas as propostas.")

# Render View Based on Active Tab
if HAS_OPTION_MENU:
    if tab1_active:
        render_tab1()
    elif tab2_active:
        render_tab2()
    elif tab3_active:
        render_tab3()
    elif tab4_active:
        render_tab4()
else:
    with tab1:
        render_tab1()
    with tab2:
        render_tab2()
    with tab3:
        render_tab3()
    with tab4:
        render_tab4()
