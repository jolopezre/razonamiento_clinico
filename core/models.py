"""Modelo de datos del paciente pediátrico.

Todas las variables de laboratorio son opcionales (None = no medido). Siguiendo
la convención de Phoenix/pSOFA, un valor no medido se puntúa como normal (0),
pero se reporta en la lista de datos faltantes para que el usuario lo sepa.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

# Soporte respiratorio (orden creciente de invasividad)
SOPORTE_RESP = {
    "ninguno": "Sin soporte (aire ambiente)",
    "o2_bajo_flujo": "O2 bajo flujo (cánula / máscara simple)",
    "caf": "Cánula de alto flujo (CAF)",
    "vni": "Ventilación no invasiva (CPAP/BiPAP)",
    "vmi": "Ventilación mecánica invasiva (VMI)",
}

# Vasoactivos que cuentan en Phoenix (dosis sistémica, cualquier dosis)
VASOACTIVOS = {
    "dopamina": "Dopamina",
    "dobutamina": "Dobutamina",
    "epinefrina": "Epinefrina (adrenalina)",
    "norepinefrina": "Norepinefrina (noradrenalina)",
    "milrinona": "Milrinona",
    "vasopresina": "Vasopresina",
}

FOCOS = {
    "nac": "Neumonía adquirida en la comunidad (NAC)",
    "sepsis_sin_foco": "Sepsis / fiebre sin foco aparente",
    "neutropenia_febril": "Neutropenia febril",
    "itu": "Infección urinaria / pielonefritis",
    "meningitis": "Meningitis / infección del SNC",
    "osteoarticular": "Infección osteoarticular",
    "piel_partes_blandas": "Piel y partes blandas",
    "cvc": "Infección asociada a catéter venoso central",
}

COMORBILIDADES = {
    "prematuridad": "Antecedente de prematuridad (<37 sem)",
    "cardiopatia": "Cardiopatía congénita",
    "pulmonar_cronica": "Enfermedad pulmonar crónica / DBP",
    "neurologica": "Enfermedad neurológica crónica (PCI, trastorno deglutorio)",
    "cancer_quimio": "Cáncer en quimioterapia",
    "tph_trasplante": "Trasplante (TPH u órgano sólido)",
    "vih": "Infección por VIH",
    "inmunosupresores": "Corticoides / inmunosupresores crónicos",
    "asplenia": "Asplenia / drepanocitosis",
    "desnutricion": "Desnutrición moderada-severa",
    "uropatia_erc": "Uropatía / enfermedad renal crónica",
    "cvc_portador": "Portador de catéter venoso central",
    "derivacion_vp": "Derivación ventrículo-peritoneal",
}

FACTORES_EPIDEMIOLOGICOS = {
    "atb_previo_30d": "Antibióticos en los últimos 30 días",
    "hosp_reciente_90d": "Hospitalización en los últimos 90 días",
    "colonizacion_blee": "Colonización/infección previa por BLEE",
    "colonizacion_sarm": "Colonización/infección previa por SARM",
    "vacunacion_incompleta": "Vacunación incompleta (Hib / neumococo)",
}


@dataclass
class Paciente:
    # --- Identificación (no ingresar nombres ni DNI: usar código anonimizado)
    codigo_registro: str = ""
    evaluador: str = ""

    # --- Demografía
    edad_meses: float = 18.0
    sexo: str = "No especificado"
    peso_kg: float = 11.0

    # --- Contexto clínico
    foco: str = "nac"
    comorbilidades: List[str] = field(default_factory=list)
    factores: List[str] = field(default_factory=list)
    notas: str = ""

    # --- Signos vitales
    temp_c: float = 38.5
    fc: int = 140
    fr: int = 40
    pas: int = 90
    pad: int = 55
    llenado_capilar_s: float = 2.0
    alteracion_conciencia: bool = False

    # --- Respiratorio
    spo2: float = 95.0
    fio2: float = 0.21
    pao2: Optional[float] = None
    soporte_resp: str = "ninguno"

    # --- Cardiovascular: {droga: dosis µg/kg/min} (dosis 0 = en uso, sin dato)
    vasoactivos: Dict[str, float] = field(default_factory=dict)
    lactato: Optional[float] = None

    # --- Coagulación
    plaquetas: Optional[float] = None       # x10^3/µL
    inr: Optional[float] = None
    dimero_d: Optional[float] = None        # mg/L FEU
    fibrinogeno: Optional[float] = None     # mg/dL

    # --- Neurológico
    glasgow: int = 15
    pupilas_fijas: bool = False

    # --- Phoenix-8 / pSOFA adicionales
    glucosa: Optional[float] = None         # mg/dL
    anc: Optional[float] = None             # neutrófilos /mm3
    alc: Optional[float] = None             # linfocitos /mm3
    creatinina: Optional[float] = None      # mg/dL
    bilirrubina: Optional[float] = None     # mg/dL
    alt: Optional[float] = None             # UI/L

    # ------------------------------------------------------------------
    @property
    def pam(self) -> float:
        """Presión arterial media estimada: (PAS + 2·PAD) / 3."""
        return round((self.pas + 2 * self.pad) / 3, 1)

    @property
    def edad_anios(self) -> float:
        return self.edad_meses / 12

    def tiene(self, clave: str) -> bool:
        return clave in self.comorbilidades or clave in self.factores

    def to_dict(self) -> dict:
        return asdict(self)
