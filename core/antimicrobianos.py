"""Tabla de dosificación pediátrica orientativa (mg/kg/día) con tope diario.

Fuentes de referencia: Red Book (AAP), Nelson's Pediatric Antimicrobial
Therapy, Harriet Lane. USO EDUCATIVO: verificar siempre con el formulario
institucional, función renal, edad gestacional/postnatal y niveles séricos.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Farmaco:
    nombre: str
    via: str
    mg_kg_dia: float
    dosis_por_dia: int
    max_mg_dia: Optional[float]
    nota: str = ""


F = Farmaco
FARMACOS = {
    "amoxicilina": F("Amoxicilina", "VO", 90, 2, 4000),
    "amoxi_clav": F("Amoxicilina/clavulánico (7:1 o 14:1)", "VO", 90, 2, 4000, "dosis por amoxicilina"),
    "azitromicina": F("Azitromicina", "VO", 10, 1, 500, "10 mg/kg día 1, luego 5 mg/kg/día días 2-5"),
    "ampicilina": F("Ampicilina", "IV", 200, 4, 12000),
    "ampicilina_snc": F("Ampicilina (dosis meníngea)", "IV", 300, 4, 12000),
    "ampi_sulbactam": F("Ampicilina/sulbactam", "IV", 200, 4, 8000, "dosis por ampicilina"),
    "ceftriaxona": F("Ceftriaxona", "IV", 75, 1, 2000, "evitar en <28 días (hiperbilirrubinemia, calcio IV)"),
    "ceftriaxona_snc": F("Ceftriaxona (dosis meníngea)", "IV", 100, 2, 4000),
    "cefotaxima": F("Cefotaxima", "IV", 150, 3, 8000, "neonatos: ajustar intervalo por edad postnatal"),
    "cefotaxima_snc": F("Cefotaxima (dosis meníngea)", "IV", 300, 4, 12000),
    "cefepime": F("Cefepime", "IV", 150, 3, 6000),
    "cefazolina": F("Cefazolina", "IV", 100, 3, 6000),
    "cefalexina": F("Cefalexina", "VO", 75, 3, 4000),
    "cefixima": F("Cefixima", "VO", 8, 1, 400),
    "gentamicina": F("Gentamicina", "IV", 7.5, 1, None, "neonatos 4-5 mg/kg/dosis; intervalo según EG y días de vida; monitorizar niveles"),
    "amikacina": F("Amikacina", "IV", 15, 1, 1500, "monitorizar función renal y niveles"),
    "vancomicina": F("Vancomicina", "IV", 60, 4, None, "ajustar por AUC/niveles valle y función renal"),
    "pip_tazo": F("Piperacilina/tazobactam", "IV", 300, 4, 16000, "dosis por piperacilina; considerar infusión extendida"),
    "meropenem": F("Meropenem", "IV", 60, 3, 3000),
    "meropenem_snc": F("Meropenem (dosis meníngea)", "IV", 120, 3, 6000),
    "clindamicina": F("Clindamicina", "IV", 40, 3, 2700),
    "tmp_smx": F("Trimetoprim/sulfametoxazol", "VO", 10, 2, 320, "dosis por TMP"),
    "aciclovir": F("Aciclovir", "IV", 60, 3, None, "dosis neonatal; ajustar por función renal"),
    "dexametasona": F("Dexametasona", "IV", 0.6, 4, 40, "0.15 mg/kg/dosis c/6h × 2-4 días; antes o con la 1.ª dosis de ATB; no en neonatos"),
}


def calcular_dosis(clave: str, peso_kg: float) -> dict:
    f = FARMACOS[clave]
    mg_dia = f.mg_kg_dia * peso_kg
    tope = f.max_mg_dia is not None and mg_dia > f.max_mg_dia
    if tope:
        mg_dia = f.max_mg_dia
    intervalo = 24 // f.dosis_por_dia
    return {
        "clave": clave,
        "farmaco": f.nombre,
        "via": f.via,
        "mg_kg_dia": f.mg_kg_dia,
        "mg_dia": round(mg_dia, 1),
        "mg_dosis": round(mg_dia / f.dosis_por_dia, 1),
        "intervalo": f"c/{intervalo}h" if f.dosis_por_dia > 1 else "c/24h",
        "tope_aplicado": tope,
        "nota": f.nota,
    }
