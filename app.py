# ==============================================================================
# APP WEB INTERACTIVA: RAZONAMIENTO CLÍNICO EN INFECTOLOGÍA PEDIÁTRICA
# ==============================================================================

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import streamlit as st
from Bio import Entrez

# ------------------------------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA Y ESTILOS
# ------------------------------------------------------------------------------
st.set_page_config(
    page_title="Razonamiento Infectológico Pediátrico",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🩺 Soporte de Decisión Clínica & Evidencia en Infectología Pediátrica")
st.markdown("""
Esta aplicación evalúa parámetros clínicos de pacientes pediátricos, calcula esquemas 
antimicrobianos orientativos y consulta automáticamente en **PubMed** la evidencia 
publicada en los **últimos 2 meses**.
""")

# ------------------------------------------------------------------------------
# BARRA LATERAL: PARÁMETROS DEL PACIENTE
# ------------------------------------------------------------------------------
st.sidebar.header("📋 Datos del Paciente")

email_usuario = st.sidebar.text_input(
    "Correo para API NCBI Entrez", 
    value="medico@institucion.edu.pe",
    help="NCBI requiere un correo de contacto para el uso de la API de PubMed."
)

edad_meses = st.sidebar.number_input("Edad (meses)", min_value=1, max_value=216, value=18, step=1)
peso_kg = st.sidebar.number_input("Peso (kg)", min_value=2.0, max_value=80.0, value=11.5, step=0.5)

st.sidebar.subheader("Signos Vitales")
temp_c = st.sidebar.slider("Temperatura (°C)", 35.0, 41.0, 38.9, 0.1)
frec_card = st.sidebar.number_input("Frecuencia Cardíaca (bpm)", 60, 220, 155)
frec_resp = st.sidebar.number_input("Frecuencia Respiratoria (rpm)", 12, 80, 52)
saturacion_o2 = st.sidebar.slider("Saturación de Oxígeno (%)", 70.0, 100.0, 90.0, 0.5)

st.sidebar.subheader("Factores de Riesgo")
foco_infeccioso = st.sidebar.selectbox(
    "Foco Infeccioso Sospechoso",
    ["Neumonía complicada / NAC", "Sepsis de origen no determinado", "Neutropenia febril", "Infección urinaria / Pielonefritis"]
)
inmunocompromiso = st.sidebar.checkbox("Inmunocompromiso", value=False)
uso_atb_previo = st.sidebar.checkbox("Uso de antibióticos en últimos 30 días", value=True)

# ------------------------------------------------------------------------------
# MÓDULO DE BÚSQUEDA AUTOMATIZADA EN PUBMED
# ------------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # Caché de 1 hora para evitar saturar la API
def buscar_evidencia_pubmed(email: str, query_terms: str, months_back: int = 2) -> pd.DataFrame:
    Entrez.email = email
    Entrez.tool = "StreamlitInfectoPedApp"
    
    end_date = datetime.now()
    start_date = end_date - relativedelta(months=months_back)
    date_filter = f'("{start_date.strftime("%Y/%m/%d")}"[Date - Publication] : "{end_date.strftime("%Y/%m/%d")}"[Date - Publication])'
    
    base_pediatric = '("Pediatrics"[Mesh] OR "Infant"[Mesh] OR "Child"[Mesh] OR pediatric*[Title/Abstract])'
    base_infecto = '("Infectious Disease Medicine"[Mesh] OR "Anti-Bacterial Agents"[Mesh] OR infection*[Title/Abstract])'
    full_query = f'{base_pediatric} AND {base_infecto} AND ({query_terms}) AND {date_filter}'
    
    try:
        search_handle = Entrez.esearch(db="pubmed", term=full_query, retmax=10, sort="pub_date")
        search_results = Entrez.read(search_handle)
        search_handle.close()
        
        id_list = search_results.get("IdList", [])
        if not id_list:
            return pd.DataFrame()
            
        fetch_handle = Entrez.efetch(db="pubmed", id=",".join(id_list), rettype="xml", retmode="xml")
        xml_data = fetch_handle.read()
        fetch_handle.close()
        
        root = ET.fromstring(xml_data)
        articles = []
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//MedlineCitation/PMID")
            title = article.findtext(".//Article/ArticleTitle") or "Sin título"
            journal = article.findtext(".//Article/Journal/Title") or "N/A"
            pub_date = article.findtext(".//Article/Journal/JournalIssue/PubDate/Year") or "Reciente"
            
            abstract_parts = article.findall(".//Article/Abstract/AbstractText")
            abstract = " ".join([p.text for p in abstract_parts if p.text]) if abstract_parts else ""
            
            doi = "N/A"
            for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if article_id.attrib.get("IdType") == "doi":
                    doi = article_id.text
                    break
            url = f"https://doi.org/{doi}" if doi != "N/A" else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            
            articles.append({"PMID": pmid, "Title": title, "Journal": journal, "Year": pub_date, "Abstract": abstract, "URL": url})
        return pd.DataFrame(articles)
    except Exception as e:
        st.error(f"Error al conectar con PubMed: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------------------
# LÓGICA DE RAZONAMIENTO CLÍNICO
# ------------------------------------------------------------------------------
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📊 Evaluación del Paciente")
    
    alertas = []
    riesgo_alto = False
    
    if saturacion_o2 < 92.0:
        alertas.append("⚠️ **Hipoxemia**: SatO2 < 92%. Requiere oxigenoterapia.")
        riesgo_alto = True
    if temp_c > 38.5:
        alertas.append(f"🌡️ **Fiebre alta**: {temp_c}°C.")
    if frec_card > 150:
        alertas.append(f"💓 **Taquicardia**: {frec_card} bpm.")
    if inmunocompromiso:
        alertas.append("🛡️ **Huésped Inmunocomprometido**: Riesgo de infecciones oportunistas.")
        riesgo_alto = True

    if alertas:
        for a in alertas:
            st.warning(a)
    else:
        st.success("Signos vitales dentro de parámetros estables.")

with col2:
    st.subheader("💊 Esquema Empírico Sugerido")
    
    esquemas = []
    dosis = []
    
    if "Neumonía" in foco_infeccioso:
        if riesgo_alto or saturacion_o2 < 92:
            esquemas.append("**Ceftriaxona IV**: 80 mg/kg/día")
            dosis.append(f"Dosis calculada: ~{(80 * peso_kg):.0f} mg/día dividido cada 12-24h")
            if uso_atb_previo or inmunocompromiso:
                esquemas.append("**Considerar Vancomicina IV**: Cobertura SAMR (40-60 mg/kg/día)")
        else:
            esquemas.append("**Amoxicilina VO**: 90 mg/kg/día")
            dosis.append(f"Dosis calculada: ~{(90 * peso_kg):.0f} mg/día dividido cada 8-12h")
    elif "Sepsis" in foco_infeccioso or "Neutropenia" in foco_infeccioso:
        esquemas.append("**Piperacilina/Tazobactam IV**: 300 mg/kg/día")
        dosis.append(f"Dosis calculada: ~{(300 * peso_kg):.0f} mg/día dividido cada 6h")

    for esq, dos in zip(esquemas, dosis):
        st.markdown(f"- {esq}")
        st.caption(f"  {dos}")

# ------------------------------------------------------------------------------
# EVIDENCIA RECIENTE PUBMED
# ------------------------------------------------------------------------------
st.divider()
st.subheader("📚 Evidencia Automatizada en PubMed (Últimos 2 Meses)")

if st.button("🔎 Buscar Evidencia Reciente en PubMed"):
    with st.spinner("Consultando la base de datos NCBI Entrez..."):
        df_pubmed = buscar_evidencia_pubmed(email_usuario, foco_infeccioso)
        
        if not df_pubmed.empty:
            st.success(f"Se encontraron {len(df_pubmed)} publicaciones recientes.")
            for _, row in df_pubmed.iterrows():
                with st.expander(f"📄 {row['Title']} ({row['Journal']}, {row['Year']})"):
                    st.write(f"**PMID:** {row['PMID']}")
                    st.write(f"**Resumen:** {row['Abstract'][:400]}...")
                    st.markdown(f"[🔗 Ver artículo completo en DOI/PubMed]({row['URL']})")
        else:
            st.info("No se encontraron publicaciones recientes para los términos específicos en los últimos 2 meses.")