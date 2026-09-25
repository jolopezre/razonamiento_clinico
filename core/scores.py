"""Puntajes de disfunción orgánica pediátrica: Phoenix Sepsis Score y pSOFA.

Referencias
-----------
* Schlapbach LJ, et al. International Consensus Criteria for Pediatric Sepsis
  and Septic Shock. JAMA 2024;331(8):665-674.
* Sanchez-Pinto LN, et al. Development and Validation of the Phoenix Criteria
  for Pediatric Sepsis and Septic Shock. JAMA 2024;331(8):675-686.
  Tablas implementadas según el paquete oficial `phoenix` (CU-DBMI-Peds).
* Matics TJ, Sanchez-Pinto LN. Adaptation and Validation of a Pediatric
  Sequential Organ Failure Assessment Score. JAMA Pediatr 2017;171(10):e172352.

Convención: laboratorios no medidos (None) puntúan 0 y se listan en `faltantes`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import Paciente

# Soporte que habilita el punto respiratorio "any respiratory support" en Phoenix
# (paquete oficial: alto flujo, VNI o VMI).
SOPORTE_PHOENIX = {"caf", "vni", "vmi"}
# Soporte requerido para puntajes 3-4 respiratorios en pSOFA
SOPORTE_PSOFA = {"vni", "vmi"}


@dataclass
class ResultadoScore:
    nombre: str
    total: int
    componentes: Dict[str, int]
    detalle: Dict[str, str] = field(default_factory=dict)
    faltantes: List[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def ratio_oxigenacion(p: Paciente) -> Tuple[Optional[str], Optional[float]]:
    """Devuelve ("PF"|"SF", valor). Prefiere PaO2:FiO2; SpO2:FiO2 solo si SpO2 ≤ 97 %."""
    fio2 = max(min(p.fio2, 1.0), 0.21)
    if p.pao2 is not None and p.pao2 > 0:
        return "PF", round(p.pao2 / fio2, 1)
    if p.spo2 is not None and p.spo2 <= 97:
        return "SF", round(p.spo2 / fio2, 1)
    return None, None


def _banda_edad(edad_meses: float, cortes: List[float]) -> int:
    """Índice de la banda de edad dada una lista de límites superiores (meses, excluyentes)."""
    for i, limite in enumerate(cortes):
        if edad_meses < limite:
            return i
    return len(cortes)


# ----------------------------------------------------------------------------
# PHOENIX SEPSIS SCORE (4 sistemas, 0-13) + PHOENIX-8 (0-20)
# ----------------------------------------------------------------------------
# PAM por edad: (umbral_1pt_inferior, umbral_2pt) -> 1 pt si PAM < umbral_0pt; 2 pt si < umbral_2pt
# Bandas: <1, 1-<12, 12-<24, 24-<60, 60-<144, 144-<216 meses
PHOENIX_PAM = [(31, 17), (39, 25), (44, 31), (45, 32), (49, 36), (52, 38)]
PHOENIX_PAM_CORTES = [1, 12, 24, 60, 144]
PHOENIX_CREAT = [0.8, 0.3, 0.4, 0.6, 0.7, 1.0]  # ≥ valor = 1 punto


def phoenix_respiratorio(p: Paciente, o2_bajo_flujo_cuenta: bool = False) -> Tuple[int, str]:
    tipo, valor = ratio_oxigenacion(p)
    soporte_valido = set(SOPORTE_PHOENIX)
    if o2_bajo_flujo_cuenta:
        soporte_valido.add("o2_bajo_flujo")
    if tipo is None:
        return 0, "Sin PaO2 y SpO2 > 97 %: no evaluable (0 pts)"
    vmi = p.soporte_resp == "vmi"
    con_soporte = p.soporte_resp in soporte_valido
    if tipo == "PF":
        c1, c2, c3 = 400, 200, 100
    else:
        c1, c2, c3 = 292, 220, 148
    if vmi and valor < c3:
        pts = 3
    elif vmi and valor < c2:
        pts = 2
    elif con_soporte and valor < c1:
        pts = 1
    else:
        pts = 0
    return pts, f"{tipo} = {valor:.0f} · soporte: {p.soporte_resp}"


def phoenix_cardiovascular(p: Paciente) -> Tuple[int, str, List[str]]:
    faltantes = []
    n_vaso = len(p.vasoactivos)
    pts_vaso = 0 if n_vaso == 0 else (1 if n_vaso == 1 else 2)

    if p.lactato is None:
        pts_lac = 0
        faltantes.append("lactato")
    else:
        pts_lac = 2 if p.lactato >= 11 else (1 if p.lactato >= 5 else 0)

    idx = _banda_edad(p.edad_meses, PHOENIX_PAM_CORTES)
    umbral0, umbral2 = PHOENIX_PAM[idx]
    pam = p.pam
    pts_pam = 2 if pam < umbral2 else (1 if pam < umbral0 else 0)

    total = pts_vaso + pts_lac + pts_pam
    det = (f"vasoactivos={n_vaso} ({pts_vaso}) · lactato={p.lactato} ({pts_lac}) · "
           f"PAM={pam} [<{umbral0}→1, <{umbral2}→2] ({pts_pam})")
    return total, det, faltantes


def phoenix_coagulacion(p: Paciente) -> Tuple[int, str, List[str]]:
    criterios = {
        "plaquetas <100": (p.plaquetas, lambda v: v < 100),
        "INR >1.3": (p.inr, lambda v: v > 1.3),
        "dímero D >2 mg/L FEU": (p.dimero_d, lambda v: v > 2),
        "fibrinógeno <100": (p.fibrinogeno, lambda v: v < 100),
    }
    positivos, faltantes = [], []
    for nombre, (valor, regla) in criterios.items():
        if valor is None:
            faltantes.append(nombre.split(" ")[0])
        elif regla(valor):
            positivos.append(nombre)
    return min(len(positivos), 2), ", ".join(positivos) or "sin criterios", faltantes


def phoenix_neurologico(p: Paciente) -> Tuple[int, str]:
    if p.pupilas_fijas:
        return 2, "pupilas fijas bilaterales"
    if p.glasgow <= 10:
        return 1, f"Glasgow {p.glasgow} ≤ 10"
    return 0, f"Glasgow {p.glasgow}"


def phoenix_8_extra(p: Paciente) -> Tuple[Dict[str, int], List[str]]:
    faltantes = []
    comp = {}
    if p.glucosa is None:
        faltantes.append("glucosa"); comp["Endocrino"] = 0
    else:
        comp["Endocrino"] = int(p.glucosa < 50 or p.glucosa > 150)

    if p.anc is None and p.alc is None:
        faltantes.append("RAN/RAL"); comp["Inmunológico"] = 0
    else:
        comp["Inmunológico"] = int((p.anc is not None and p.anc < 500) or
                                   (p.alc is not None and p.alc < 1000))

    if p.creatinina is None:
        faltantes.append("creatinina"); comp["Renal"] = 0
    else:
        idx = _banda_edad(p.edad_meses, PHOENIX_PAM_CORTES)
        comp["Renal"] = int(p.creatinina >= PHOENIX_CREAT[idx])

    if p.bilirrubina is None and p.alt is None:
        faltantes.append("bilirrubina/ALT"); comp["Hepático"] = 0
    else:
        comp["Hepático"] = int((p.bilirrubina is not None and p.bilirrubina >= 4) or
                               (p.alt is not None and p.alt > 102))
    return comp, faltantes


@dataclass
class ResultadoPhoenix(ResultadoScore):
    phoenix8: int = 0
    componentes8: Dict[str, int] = field(default_factory=dict)
    sepsis: bool = False
    choque_septico: bool = False


def calcular_phoenix(p: Paciente, infeccion_sospechada: bool = True,
                     o2_bajo_flujo_cuenta: bool = False) -> ResultadoPhoenix:
    r_pts, r_det = phoenix_respiratorio(p, o2_bajo_flujo_cuenta)
    c_pts, c_det, c_falt = phoenix_cardiovascular(p)
    k_pts, k_det, k_falt = phoenix_coagulacion(p)
    n_pts, n_det = phoenix_neurologico(p)
    comp = {"Respiratorio": r_pts, "Cardiovascular": c_pts,
            "Coagulación": k_pts, "Neurológico": n_pts}
    total = sum(comp.values())
    extra, e_falt = phoenix_8_extra(p)
    comp8 = {**comp, **extra}
    sepsis = infeccion_sospechada and total >= 2
    return ResultadoPhoenix(
        nombre="Phoenix Sepsis Score",
        total=total,
        componentes=comp,
        detalle={"Respiratorio": r_det, "Cardiovascular": c_det,
                 "Coagulación": k_det, "Neurológico": n_det},
        faltantes=c_falt + k_falt + e_falt,
        phoenix8=sum(comp8.values()),
        componentes8=comp8,
        sepsis=sepsis,
        choque_septico=sepsis and c_pts >= 1,
    )


# ----------------------------------------------------------------------------
# pSOFA (6 sistemas, 0-24)
# ----------------------------------------------------------------------------
PSOFA_CORTES = [1, 12, 24, 60, 144, 216]
PSOFA_PAM = [46, 55, 60, 62, 65, 67, 70]
# Límite inferior (mg/dL) para 1, 2, 3 y 4 puntos, por banda de edad
PSOFA_CREAT = [
    (0.8, 1.0, 1.2, 1.6),
    (0.3, 0.5, 0.8, 1.2),
    (0.4, 0.6, 1.1, 1.5),
    (0.6, 0.9, 1.6, 2.3),
    (0.7, 1.1, 1.8, 2.6),
    (1.0, 1.7, 2.9, 4.2),
    (1.2, 2.0, 3.5, 5.0),
]


def _por_escalones(valor: float, limites_inferiores: Tuple[float, ...]) -> int:
    """Puntos = número de límites superados (valor ≥ límite)."""
    return sum(valor >= lim for lim in limites_inferiores)


def psofa_respiratorio(p: Paciente) -> Tuple[int, str]:
    tipo, valor = ratio_oxigenacion(p)
    if tipo is None:
        return 0, "no evaluable (sin PaO2 y SpO2 > 97 %)"
    cortes = (400, 300, 200, 100) if tipo == "PF" else (292, 264, 221, 148)
    pts = sum(valor < c for c in cortes)
    if pts >= 3 and p.soporte_resp not in SOPORTE_PSOFA:
        pts = 2  # 3-4 puntos exigen soporte ventilatorio
    return pts, f"{tipo} = {valor:.0f}"


def psofa_cardiovascular(p: Paciente) -> Tuple[int, str]:
    v = p.vasoactivos
    dopa, epi, nore = v.get("dopamina"), v.get("epinefrina"), v.get("norepinefrina")
    if (dopa is not None and dopa > 15) or (epi is not None and epi > 0.1) or \
       (nore is not None and nore > 0.1):
        return 4, "dopamina >15 o epi/norepi >0.1 µg/kg/min"
    if (dopa is not None and dopa > 5) or epi is not None or nore is not None:
        return 3, "dopamina >5 o epi/norepi ≤0.1 µg/kg/min"
    if dopa is not None or "dobutamina" in v:
        return 2, "dopamina ≤5 o dobutamina"
    umbral = PSOFA_PAM[_banda_edad(p.edad_meses, PSOFA_CORTES)]
    if p.pam < umbral:
        return 1, f"PAM {p.pam} < {umbral}"
    return 0, f"PAM {p.pam} ≥ {umbral}"


def calcular_psofa(p: Paciente) -> ResultadoScore:
    faltantes = []
    r_pts, r_det = psofa_respiratorio(p)
    c_pts, c_det = psofa_cardiovascular(p)

    if p.plaquetas is None:
        k_pts, k_det = 0, "no medido"; faltantes.append("plaquetas")
    else:
        k_pts = sum(p.plaquetas < c for c in (150, 100, 50, 20))
        k_det = f"plaquetas {p.plaquetas:g}"

    if p.bilirrubina is None:
        h_pts, h_det = 0, "no medido"; faltantes.append("bilirrubina")
    else:
        h_pts = _por_escalones(p.bilirrubina, (1.2, 2.0, 6.0, 12.0))
        h_det = f"bilirrubina {p.bilirrubina:g}"

    g = p.glasgow
    n_pts = 0 if g >= 15 else 1 if g >= 13 else 2 if g >= 10 else 3 if g >= 6 else 4

    if p.creatinina is None:
        rn_pts, rn_det = 0, "no medido"; faltantes.append("creatinina")
    else:
        limites = PSOFA_CREAT[_banda_edad(p.edad_meses, PSOFA_CORTES)]
        rn_pts = _por_escalones(p.creatinina, limites)
        rn_det = f"creatinina {p.creatinina:g} (cortes por edad {limites})"

    comp = {"Respiratorio": r_pts, "Cardiovascular": c_pts, "Coagulación": k_pts,
            "Hepático": h_pts, "Neurológico": n_pts, "Renal": rn_pts}
    return ResultadoScore(
        nombre="pSOFA", total=sum(comp.values()), componentes=comp,
        detalle={"Respiratorio": r_det, "Cardiovascular": c_det, "Coagulación": k_det,
                 "Hepático": h_det, "Neurológico": f"Glasgow {g}", "Renal": rn_det},
        faltantes=faltantes,
    )
