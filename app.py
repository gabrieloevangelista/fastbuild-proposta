"""
Orça Rápido Monolítico — Calculadora de Instalação por Metragem de Parede em Painéis EPS
======================================================================================
"""
import os
import tempfile
import urllib.request
import json
import textwrap
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

# ----------------------------------------------------------------- SVG Outline Icons Helper
def icon(name: str, size: int = 18, color: str = "currentColor") -> str:
    icons = {
        "file-cad": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M8 13h8"/><path d="M8 17h8"/><path d="M10 9h2"/></svg>',
        "ruler": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0l12.6 12.6z"/><path d="m14.5 12.5 2-2"/><path d="m11.5 9.5 2-2"/><path d="m8.5 6.5 2-2"/><path d="m17.5 15.5 2-2"/></svg>',
        "building": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M12 6h.01"/><path d="M12 10h.01"/><path d="M12 14h.01"/><path d="M16 10h.01"/><path d="M16 14h.01"/><path d="M8 10h.01"/><path d="M8 14h.01"/></svg>',
        "user": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
        "terms": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 6v12"/></svg>',
        "download": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        "check": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        "warning": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        "search": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
        "upload": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>',
        "pdf": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><path d="M10 12a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1"/><path d="M10 12h2a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1h-2"/><path d="M16 12h-2v6"/></svg>',
        "gear": f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 6px;"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>'
    }
    return icons.get(name, "")

# ----------------------------------------------------------------- Custom CSS
st.markdown(
    textwrap.dedent("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    }

    .stApp {
        background-color: #f8fafc;
        color: #0f172a;
    }

    /* Minimalist White Label Header */
    .header-container {
        display: flex;
        align-items: center;
        gap: 16px;
        background: #ffffff;
        padding: 18px 24px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }

    .header-logo-preview img {
        max-height: 46px;
        width: auto;
        border-radius: 6px;
    }

    .header-title-text {
        font-size: 22px;
        font-weight: 800;
        color: #0f172a;
        margin: 0;
        letter-spacing: -0.3px;
        display: flex;
        align-items: center;
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
        border-radius: 10px;
        border: 1px solid #e2e8f0;
    }

    .stTabs [data-baseweb="tab"] {
        height: 40px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 13px;
        color: #64748b;
        padding: 0 18px;
        border: none;
    }

    .stTabs [aria-selected="true"] {
        background-color: #0d9488 !important;
        color: #ffffff !important;
    }

    /* Modern Card Containers */
    .custom-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 20px 24px;
        border: 1px solid #e2e8f0;
        margin-bottom: 18px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
    }

    .card-title-html {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
    }

    /* KPI Summary Cards */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin-bottom: 18px;
    }

    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
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
        margin-top: 2px;
    }

    /* Outline Badges */
    .badge {
        display: inline-flex;
        align-items: center;
        padding: 3px 10px;
        border-radius: 9999px;
        font-size: 12px;
        font-weight: 600;
    }

    .badge-success {
        background-color: #f0fdf4;
        color: #15803d;
        border: 1px solid #bbf7d0;
    }

    .badge-danger {
        background-color: #fef2f2;
        color: #b91c1c;
        border: 1px solid #fecaca;
    }

    /* Primary Buttons */
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
    """),
    unsafe_allow_html=True,
)

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

# Render Header with Custom Saved Logo if available
logo_header_html = ""
if st.session_state.get("saved_logo_path") and os.path.exists(st.session_state.saved_logo_path):
    try:
        with open(st.session_state.saved_logo_path, "rb") as img_file:
            enc = base64.b64encode(img_file.read()).decode()
        logo_header_html = f'<div class="header-logo-preview"><img src="data:image/png;base64,{enc}" alt="Company Logo" /></div>'
    except Exception:
        pass

company_display_title = st.session_state.default_company.get("nome") or "Orça Rápido Monolítico"

st.markdown(
    textwrap.dedent(f"""
    <div class="header-container">
        {logo_header_html}
        <div>
            <div class="header-title-text">{icon('ruler', 22, '#0d9488')} {company_display_title}</div>
            <div class="header-subtitle">Medição Vetorial de Paredes em Painéis EPS & Orçamentos Automatizados</div>
        </div>
    </div>
    """),
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
        "Planta & Medição",
        "Empresa & Cliente",
        "Condições & Gerar PDF",
        "Configurações"
    ])
    tab1_active, tab2_active, tab3_active, tab4_active = True, True, True, True

# ----------------------------------------------------------------- Tab 1: Planta & Medição
def render_tab1():
    st.markdown(f'<div class="card-title-html">{icon("upload", 18, "#0d9488")} Upload da Planta Baixa</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Selecione o arquivo da planta (.dwg ou .dxf)",
        type=["dwg", "dxf"],
        help="Arquivos DWG são convertidos automaticamente para DXF.",
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
        st.markdown(f'<div class="card-title-html">{icon("ruler", 18, "#0d9488")} Resumo da Medição Automatizada</div>', unsafe_allow_html=True)

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
            textwrap.dedent(f"""
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
            """),
            unsafe_allow_html=True,
        )

        st.markdown(f'<div class="card-title-html">{icon("file-cad", 18, "#0d9488")} Camadas de Parede Identificadas</div>', unsafe_allow_html=True)
        for layer_name, r in st.session_state.summary.items():
            is_rev = "REV" in layer_name.upper()
            badge_html = (
                f'<span class="badge badge-danger">{icon("warning", 13, "#b91c1c")} Revestimento</span>'
                if is_rev
                else f'<span class="badge badge-success">{icon("check", 13, "#15803d")} Parede Estrutural</span>'
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

                    if st.button("Gerar overlay de conferência", key=f"overlay_{layer_name}"):
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
        st.markdown(
            textwrap.dedent(f"""
            <div class="custom-card">
                <div class="card-title-html">{icon("building", 18, "#0d9488")} Empresa Contratada (Remetente)</div>
            """),
            unsafe_allow_html=True,
        )
        
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
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(
            textwrap.dedent(f"""
            <div class="custom-card">
                <div class="card-title-html">{icon("user", 18, "#0d9488")} Cliente Contratante</div>
            """),
            unsafe_allow_html=True,
        )
        
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
        st.markdown("</div>", unsafe_allow_html=True)

# ----------------------------------------------------------------- Tab 3: Condições & Gerar PDF
def render_tab3():
    st.markdown(
        textwrap.dedent(f"""
        <div class="custom-card">
            <div class="card-title-html">{icon("terms", 18, "#0d9488")} Condições Comerciais</div>
        """),
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
        placeholder="Ex: Instalação de painéis monolíticos EPS conforme especificações técnicas do fabricante.",
        key="comm_obs",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f'<div class="card-title-html">{icon("pdf", 18, "#0d9488")} Emissão da Proposta em PDF</div>', unsafe_allow_html=True)

    if st.button("Gerar Proposta Comercial em PDF", type="primary", use_container_width=True):
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
            f"Proposta gerada com sucesso! Metragem: **{budget.total_length_m:.2f} m** | "
            f"Valor Total: **{format_brl(budget.total_value)}**"
        )

        cli_filename = (st.session_state.get('cli_nome') or 'Cliente').replace(' ', '_')
        st.download_button(
            "Baixar Proposta Comercial em PDF",
            data=pdf_bytes,
            file_name=f"Proposta_Monolitico_{cli_filename}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# ----------------------------------------------------------------- Tab 4: Configurações (Logo & Dados Padrão)
def render_tab4():
    st.markdown(
        textwrap.dedent(f"""
        <div class="custom-card">
            <div class="card-title-html">{icon("gear", 18, "#0d9488")} Configurações da Empresa & Logotipo Padrão</div>
            <p style="font-size: 13px; color: #64748b;">
                Cadastre o logotipo e os dados padrão da sua empresa. As informações salvas aqui serão pré-carregadas automaticamente em todas as novas propostas e impressas no PDF.
            </p>
        """),
        unsafe_allow_html=True,
    )

    col_logo1, col_logo2 = st.columns([1, 2])
    with col_logo1:
        st.markdown("**Logotipo Atual:**")
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
    st.markdown('<div class="card-title-html">Dados Padrão da Empresa (Remetente)</div>', unsafe_allow_html=True)

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

    st.markdown("</div>", unsafe_allow_html=True)

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
