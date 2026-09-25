"""Búsqueda automatizada de evidencia reciente en PubMed (NCBI Entrez E-utilities)."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from Bio import Entrez
from dateutil.relativedelta import relativedelta

# Foco clínico -> términos MeSH / texto libre en inglés
TERMINOS_FOCO = {
    "nac": '"Pneumonia"[Mesh] OR "community-acquired pneumonia"[tiab]',
    "sepsis_sin_foco": '"Sepsis"[Mesh] OR "Shock, Septic"[Mesh] OR sepsis[tiab]',
    "neutropenia_febril": '"Febrile Neutropenia"[Mesh] OR "febrile neutropenia"[tiab]',
    "itu": '"Urinary Tract Infections"[Mesh] OR "Pyelonephritis"[Mesh]',
    "meningitis": '"Meningitis, Bacterial"[Mesh] OR "Encephalitis"[Mesh] OR meningitis[tiab]',
    "osteoarticular": '"Osteomyelitis"[Mesh] OR "Arthritis, Infectious"[Mesh]',
    "piel_partes_blandas": '"Soft Tissue Infections"[Mesh] OR "Skin Diseases, Bacterial"[Mesh] OR cellulitis[tiab]',
    "cvc": '"Catheter-Related Infections"[Mesh] OR CLABSI[tiab]',
}
TERMINOS_EXTRA = {
    "phoenix": '"Phoenix sepsis"[tiab] OR "pSOFA"[tiab] OR "organ dysfunction"[tiab]',
    "resistencia": '"Drug Resistance, Bacterial"[Mesh] OR "beta-Lactamases"[Mesh] OR "Antimicrobial Stewardship"[Mesh]',
}
BASE_PEDIATRICA = '("Child"[Mesh] OR "Infant"[Mesh] OR "Adolescent"[Mesh] OR pediatric*[tiab] OR paediatric*[tiab] OR neonat*[tiab])'


def construir_query(foco: str, meses: int = 2, extras: Optional[List[str]] = None,
                    hoy: Optional[datetime] = None) -> str:
    hoy = hoy or datetime.now()
    inicio = hoy - relativedelta(months=meses)
    fecha = f'("{inicio:%Y/%m/%d}"[dp] : "{hoy:%Y/%m/%d}"[dp])'
    bloques = [BASE_PEDIATRICA, f"({TERMINOS_FOCO[foco]})"]
    for e in extras or []:
        bloques.append(f"({TERMINOS_EXTRA[e]})")
    return " AND ".join(bloques + [fecha])


def _parsear(xml_bytes: bytes) -> pd.DataFrame:
    root = ET.fromstring(xml_bytes)
    filas = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        titulo = "".join(art.find(".//Article/ArticleTitle").itertext()) \
            if art.find(".//Article/ArticleTitle") is not None else "Sin título"
        revista = art.findtext(".//Article/Journal/ISOAbbreviation") or \
            art.findtext(".//Article/Journal/Title") or "N/A"
        anio = art.findtext(".//Article/Journal/JournalIssue/PubDate/Year") or \
            (art.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
        resumen = " ".join("".join(t.itertext()) for t in art.findall(".//Article/Abstract/AbstractText"))
        tipos = [t.text for t in art.findall(".//PublicationTypeList/PublicationType") if t.text]
        doi = next((i.text for i in art.findall(".//PubmedData/ArticleIdList/ArticleId")
                    if i.attrib.get("IdType") == "doi"), None)
        filas.append({
            "PMID": pmid, "Titulo": titulo, "Revista": revista, "Anio": anio,
            "Tipo": ", ".join(tipos[:2]), "Resumen": resumen,
            "URL": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "DOI": doi or "",
        })
    return pd.DataFrame(filas)


def buscar_pubmed(query: str, email: str, api_key: Optional[str] = None,
                  max_resultados: int = 10, reintentos: int = 3) -> Tuple[pd.DataFrame, Optional[str]]:
    """Devuelve (DataFrame, mensaje_error). No lanza excepciones."""
    Entrez.email = email
    Entrez.tool = "RazonamientoClinicoPedApp"
    if api_key:
        Entrez.api_key = api_key
    ultimo_error = None
    for intento in range(reintentos):
        try:
            with Entrez.esearch(db="pubmed", term=query, retmax=max_resultados, sort="pub_date") as h:
                ids = Entrez.read(h).get("IdList", [])
            if not ids:
                return pd.DataFrame(), None
            time.sleep(0.34)  # ≤3 solicitudes/s sin API key
            with Entrez.efetch(db="pubmed", id=",".join(ids), rettype="xml", retmode="xml") as h:
                return _parsear(h.read()), None
        except Exception as exc:  # red, HTTP 429, XML malformado
            ultimo_error = str(exc)
            time.sleep(1.5 * (intento + 1))
    return pd.DataFrame(), ultimo_error


def vincular_evidencia(df: pd.DataFrame, farmacos: List[str]) -> pd.DataFrame:
    """Marca los artículos que mencionan los antimicrobianos del esquema sugerido."""
    if df.empty:
        return df
    equivalencias = {
        "Ceftriaxona": "ceftriaxone", "Cefotaxima": "cefotaxime", "Cefepime": "cefepime",
        "Ampicilina": "ampicillin", "Amoxicilina": "amoxicillin", "Vancomicina": "vancomycin",
        "Meropenem": "meropenem", "Piperacilina": "piperacillin", "Gentamicina": "gentamicin",
        "Amikacina": "amikacin", "Clindamicina": "clindamycin", "Cefazolina": "cefazolin",
        "Aciclovir": "acyclovir", "Cefixima": "cefixime", "Cefalexina": "cephalexin",
        "Azitromicina": "azithromycin", "Trimetoprim": "trimethoprim", "Dexametasona": "dexamethasone",
    }
    buscados = {equivalencias[k] for f in farmacos for k in equivalencias if f.startswith(k)}
    texto = (df["Titulo"] + " " + df["Resumen"]).str.lower()
    df = df.copy()
    df["Menciona"] = texto.apply(lambda t: ", ".join(sorted(b for b in buscados if b in t)))
    return df
