import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

# SEC EDGAR API configuration
USER_AGENT = "TrionicMachineExplorer <trionicmachine@hotmail.com>"

# --- UI CONFIGURATION ---
st.set_page_config(
    page_title="SEC Explorer", 
    layout="wide", 
    page_icon="🏦",
    initial_sidebar_state="expanded"
)

# Custom CSS for UI spacing
st.markdown("""
    <style>
    .stMetric {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #cccccc33;
    }
    .stDataFrame {
        border-radius: 10px;
    }
    div[data-testid="stExpander"] {
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def format_currency(value):
    if abs(value) >= 1e9:
        return f"${value / 1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.2f}"

@st.cache_data
def get_cik_mapping():
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return {v['ticker']: str(v['cik_str']).zfill(10) for k, v in data.items()}
    except Exception as e:
        st.error(f"Error cargando mapeo de CIK: {e}")
    return {}

@st.cache_data
def get_company_facts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers)
    return response.json() if response.status_code == 200 else None

@st.cache_data
def get_submissions(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers)
    return response.json() if response.status_code == 200 else None

# --- APP LAYOUT ---
# (Removing old main title as requested)

# Sidebar
with st.sidebar:
    st.header("🐸 SEC Explorer")
    ticker = st.text_input("Ticker Symbol", "AAPL").upper()
    
    cik_map = get_cik_mapping()
    cik = cik_map.get(ticker)
    
    if cik:
        st.success(f"CIK: {cik}")
    else:
        st.error("Ticker no encontrado.")
    
    st.markdown("---")
    st.caption("Trionic 2026")

if cik:
    with st.spinner(f"Analizando {ticker}..."):
        facts = get_company_facts(cik)
        subs = get_submissions(cik)
        
        if facts and subs:
            # --- HEADER / PROFILE ---
            name = facts.get('entityName', ticker)
            industry = subs.get('sicDescription', 'N/A')
            website = subs.get('website', '')
            
            # NUEVO TÍTULO DINÁMICO
            st.title(f"🏢 {name} ({ticker})")
            
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                st.write(f"**Industria:** {industry}")
            with col_h2:
                if website:
                    st.link_button("🌐 Sitio Web", f"https://{website}" if not website.startswith('http') else website)

            # Merge all available taxonomies (us-gaap and dei)
            all_facts = facts.get('facts', {})
            merged_metrics = {**all_facts.get('dei', {}), **all_facts.get('us-gaap', {})}

            # --- SECCIÓN 1: TIMELINE ---
            with st.expander("📅 Cronología de Presentaciones (10-K / 10-Q)", expanded=False):
                recent = subs.get('filings', {}).get('recent', {})
                df_f = pd.DataFrame(recent)
                df_core = df_f[df_f['form'].isin(['10-K', '10-Q'])].copy()
                
                def make_url(acc, doc):
                    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"
                
                df_core['Enlace'] = [make_url(a, p) for a, p in zip(df_core['accessionNumber'], df_core['primaryDocument'])]
                st.dataframe(
                    df_core[['filingDate', 'form', 'Enlace']].head(10),
                    column_config={"Enlace": st.column_config.LinkColumn()},
                    hide_index=True, use_container_width=True
                )

            # --- SECCIÓN 2: EXPORTACIÓN ---
            with st.expander("📥 Opciones de Exportación"):
                @st.cache_data
                def convert_all_to_csv(metrics_dict, forms_filter=None):
                    all_rows = []
                    for metric_name, data in metrics_dict.items():
                        label = data.get('label', metric_name)
                        units = data.get('units', {})
                        for unit_name, datapoints in units.items():
                            for dp in datapoints:
                                # Filtrar por formularios si se solicita
                                if forms_filter and dp.get('form') not in forms_filter:
                                    continue
                                    
                                all_rows.append({
                                    "Métrica": metric_name,
                                    "Descripción": label,
                                    "Unidad": unit_name,
                                    "Fecha": dp.get('end'),
                                    "Valor": dp.get('val'),
                                    "Formulario": dp.get('form'),
                                    "Periodo": dp.get('fp', ''),
                                    "Año": dp.get('fy', '')
                                })
                    return pd.DataFrame(all_rows)

                export_forms = st.multiselect("Filtrar formularios para el CSV", 
                                             ["10-K", "10-Q", "8-K", "S-1", "Other"],
                                             default=["10-K", "10-Q"],
                                             help="Selecciona qué tipos de reportes incluir en el archivo descargable.")
                
                df_all = convert_all_to_csv(merged_metrics, export_forms)
                st.write(f"Filas a exportar: `{len(df_all)}` (Conceptos US-GAAP / DEI)")
                
                st.download_button(
                    label="💾 Descargar Histórico Consolidado (CSV)",
                    data=df_all.to_csv(index=False).encode('utf-8'),
                    file_name=f"Master_Data_{ticker}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime='text/csv',
                    use_container_width=True
                )
            
            # Nota sobre exportación debajo del expander
            st.info("""
            💡 **Nota sobre la exportación:** El archivo CSV generado contiene el historial completo de **todas** las métricas disponibles (P&L, Balance, Cash Flow) extraídas de todos los formularios (10-K, 10-Q, 8-K) presentados por la empresa hasta la fecha.
            """)

            # --- SECCIÓN 3: VARIABLE ANALYSIS ---
            st.subheader("📈 Análisis de Variables")
            
            CATEGORIES = {
                "📅 Rendimiento (P&L)": ["NetIncomeLoss", "Revenues", "SalesRevenueNet", "OperatingIncomeLoss", "GrossProfit", "EarningsPerShareBasic"],
                "💰 Flujo de Caja": ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInFinancingActivities", "CashAndCashEquivalentsAtCarryingValue"],
                "🏛️ Balance": ["Assets", "Liabilities", "StockholdersEquity", "AssetsCurrent", "LiabilitiesCurrent"],
                "📉 Acciones/Dividendos": ["CommonStockSharesOutstanding", "Dividends", "PaymentsOfDividendsCommonStock"]
            }
            
            m_col1, m_col2 = st.columns([1, 2])
            with m_col1:
                mode = st.radio("Método de Selección", ["Categoría", "Búsqueda Libre"], horizontal=True)
                
                selected = None
                if mode == "Categoría":
                    cat = st.selectbox("Elija Categoría", list(CATEGORIES.keys()))
                    options = [m for m in CATEGORIES[cat] if m in merged_metrics]
                    selected = st.selectbox("Seleccione Métrica", options if options else ["N/A"])
                else:
                    search_query = st.text_input("🔍 Buscar métrica (ej: Revenue, Profit)", "").lower()
                    all_metrics = sorted(list(merged_metrics.keys()))
                    if search_query:
                        filtered = [
                            m for m in all_metrics 
                            if search_query in m.lower() or 
                            search_query in (merged_metrics[m].get('label') or '').lower()
                        ]
                        if filtered:
                            selected = st.selectbox(f"Coincidencias ({len(filtered)})", filtered)
                        else:
                            st.warning("No se encontraron resultados.")
                    else:
                        selected = st.selectbox("Todas las métricas", all_metrics)

            if selected and selected != "N/A":
                m_info = merged_metrics[selected]
                # Descripción en un contenedor destacado
                st.info(f"**{m_info.get('label', selected)}**: {m_info.get('description', 'Sin descripción.')}")

                # Filtro de Formularios y Gráfico
                u_data = m_info.get('units', {})
                if u_data:
                    u_key = list(u_data.keys())[0]
                    df_m = pd.DataFrame(u_data[u_key])
                    
                    form_col, _ = st.columns([2, 2])
                    with form_col:
                        f_forms = st.multiselect("Filtrar por Formularios", 
                                                df_m['form'].unique(), 
                                                default=[f for f in ['10-K', '10-Q'] if f in df_m['form'].values])
                    
                    df_p = df_m[df_m['form'].isin(f_forms)].copy()
                    df_p['end'] = pd.to_datetime(df_p['end'])
                    df_p = df_p.sort_values('end').drop_duplicates(subset=['end', 'val'], keep='last')
                    
                    fig = px.area(df_p, x='end', y='val', color='form',
                                 title=f"Evolución Histórica: {selected}",
                                 line_group='form',
                                 labels={'end': 'Fecha', 'val': u_key},
                                 template="plotly_dark")
                    fig.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', 
                                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig, use_container_width=True)
                    
                    with st.expander("📝 Ver Tabla de Datos"):
                        st.dataframe(df_p.sort_values('end', ascending=False), use_container_width=True, hide_index=True)
            
        else:
            st.error("No se pudieron obtener datos para este Ticker.")
else:
    st.info("👈 Introduce un Ticker en la barra lateral para comenzar el análisis.")
