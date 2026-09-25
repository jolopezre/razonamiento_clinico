"""Motor de razonamiento clínico infectológico pediátrico.

Integra edad, comorbilidades, factores epidemiológicos, foco y los puntajes
Phoenix/pSOFA para construir un escenario de razonamiento estructurado:

1. Representación del problema (resumen en una línea)
2. Estratificación de gravedad
3. Etiologías probables según edad y huésped
4. Estudios sugeridos
5. Esquema empírico con dosis por peso (con tope)
6. Banderas rojas y sesgos cognitivos a vigilar
7. Preguntas de razonamiento (docencia)
8. Escenarios alternativos "¿y si...?" (contrafactuales recalculados)

USO EDUCATIVO. No reemplaza el juicio clínico ni las guías institucionales.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from .antimicrobianos import calcular_dosis
from .models import COMORBILIDADES, FOCOS, Paciente
from .scores import ResultadoPhoenix, ResultadoScore, calcular_phoenix, calcular_psofa

# ----------------------------------------------------------------------------
# Edad y signos vitales (Goldstein B, et al. Pediatr Crit Care Med 2005)
# ----------------------------------------------------------------------------
# (límite superior en meses, etiqueta, FC máx, FC mín o None, FR máx)
GRUPOS_ETARIOS = [
    (0.25, "recién nacido (0-7 días)", 180, 100, 50),
    (1, "neonato (1 semana-1 mes)", 180, 100, 40),
    (24, "lactante (1 mes-2 años)", 180, 90, 34),
    (72, "preescolar (2-5 años)", 140, None, 22),
    (156, "escolar (6-12 años)", 130, None, 18),
    (10_000, "adolescente (13-18 años)", 110, None, 14),
]


def grupo_etario(edad_meses: float) -> dict:
    for limite, etiqueta, fc_max, fc_min, fr_max in GRUPOS_ETARIOS:
        if edad_meses < limite:
            return {"etiqueta": etiqueta, "fc_max": fc_max, "fc_min": fc_min, "fr_max": fr_max}
    raise ValueError("edad fuera de rango")


def describir_edad(edad_meses: float) -> str:
    if edad_meses < 1:
        return f"{round(edad_meses * 30.4)} días"
    if edad_meses < 24:
        return f"{edad_meses:g} meses"
    anios, meses = divmod(int(edad_meses), 12)
    return f"{anios} años" + (f" {meses} meses" if meses else "")


# ----------------------------------------------------------------------------
# Perfil de riesgo del huésped
# ----------------------------------------------------------------------------
@dataclass
class PerfilRiesgo:
    inmunocomprometido: bool
    riesgo_blee: bool
    riesgo_sarm: bool
    asociado_atencion_salud: bool
    riesgo_aspiracion: bool
    riesgo_encapsulados: bool
    neutropenia: bool
    motivos: List[str] = field(default_factory=list)


def perfil_riesgo(p: Paciente) -> PerfilRiesgo:
    inmuno_keys = {"cancer_quimio", "tph_trasplante", "vih", "inmunosupresores"}
    neutropenia = p.anc is not None and p.anc < 500
    inmuno = bool(inmuno_keys & set(p.comorbilidades)) or neutropenia
    aas = any(p.tiene(k) for k in ("hosp_reciente_90d", "cvc_portador", "derivacion_vp")) \
        or p.foco == "cvc"
    blee = p.tiene("colonizacion_blee") or (aas and p.tiene("atb_previo_30d")) \
        or (p.tiene("uropatia_erc") and p.tiene("atb_previo_30d"))
    sarm = p.tiene("colonizacion_sarm") or p.tiene("cvc_portador") or p.foco == "cvc"
    motivos = []
    if inmuno:
        motivos.append("huésped inmunocomprometido")
    if neutropenia:
        motivos.append(f"neutropenia (RAN {p.anc:g}/mm³)")
    if aas:
        motivos.append("exposición a la atención de salud / dispositivos")
    if blee:
        motivos.append("riesgo de enterobacterias BLEE")
    if sarm:
        motivos.append("riesgo de S. aureus resistente a meticilina")
    return PerfilRiesgo(
        inmunocomprometido=inmuno, riesgo_blee=blee, riesgo_sarm=sarm,
        asociado_atencion_salud=aas,
        riesgo_aspiracion=p.tiene("neurologica"),
        riesgo_encapsulados=p.tiene("asplenia") or p.tiene("vacunacion_incompleta"),
        neutropenia=neutropenia, motivos=motivos,
    )


# ----------------------------------------------------------------------------
# Etiologías por foco y edad
# ----------------------------------------------------------------------------
def etiologias(p: Paciente, r: PerfilRiesgo) -> List[str]:
    e = p.edad_meses
    neonato = e < 1
    lactante_pequeno = e < 3
    out: List[str] = []
    if p.foco == "nac":
        if neonato:
            out = ["Streptococcus agalactiae (SGB)", "E. coli y otras enterobacterias",
                   "Listeria monocytogenes", "virus (VSR, VHS en neumonitis grave)"]
        elif lactante_pequeno:
            out = ["virus respiratorios (VSR, metapneumovirus)", "S. pneumoniae",
                   "Chlamydia trachomatis (afebril, conjuntivitis)", "Bordetella pertussis"]
        elif e < 60:
            out = ["virus respiratorios (causa más frecuente)", "S. pneumoniae",
                   "H. influenzae (si vacunación incompleta)", "S. aureus (neumonía necrotizante/empiema)"]
        else:
            out = ["S. pneumoniae", "Mycoplasma pneumoniae", "Chlamydia pneumoniae",
                   "virus respiratorios", "S. aureus (post-influenza, necrotizante)"]
        if r.riesgo_aspiracion:
            out.append("anaerobios orales (neumonía aspirativa)")
        if r.inmunocomprometido:
            out += ["Pseudomonas aeruginosa", "Pneumocystis jirovecii", "hongos filamentosos (Aspergillus)"]
    elif p.foco in ("sepsis_sin_foco", "cvc"):
        if neonato:
            out = ["SGB", "E. coli", "Listeria monocytogenes", "virus herpes simple", "enterovirus"]
        elif lactante_pequeno:
            out = ["E. coli (ITU oculta)", "SGB tardío", "S. pneumoniae", "enterovirus"]
        else:
            out = ["S. pneumoniae", "N. meningitidis", "S. aureus", "Streptococcus pyogenes"]
        if p.foco == "cvc" or r.asociado_atencion_salud:
            out += ["estafilococos coagulasa negativo", "S. aureus (incl. SARM)",
                    "bacilos gramnegativos (Klebsiella, Pseudomonas)", "Candida spp."]
    elif p.foco == "neutropenia_febril":
        out = ["bacilos gramnegativos (E. coli, Klebsiella, P. aeruginosa)",
               "Streptococcus viridans (mucositis)", "S. aureus / estafilococos coagulasa negativo (CVC)",
               "hongos (Candida, Aspergillus) si fiebre persistente >96 h"]
    elif p.foco == "itu":
        out = ["E. coli (80-90 %)", "Klebsiella spp.", "Proteus mirabilis", "Enterococcus faecalis"]
        if neonato or lactante_pequeno:
            out.append("considerar bacteriemia concomitante (alta en <3 meses)")
        if p.tiene("uropatia_erc"):
            out += ["Pseudomonas aeruginosa", "enterobacterias BLEE"]
    elif p.foco == "meningitis":
        if neonato:
            out = ["SGB", "E. coli", "Listeria monocytogenes", "virus herpes simple", "enterovirus"]
        elif lactante_pequeno:
            out = ["SGB", "E. coli", "S. pneumoniae", "N. meningitidis", "enterovirus"]
        else:
            out = ["S. pneumoniae", "N. meningitidis", "H. influenzae b (no vacunados)", "enterovirus"]
        if p.tiene("derivacion_vp"):
            out += ["estafilococos coagulasa negativo", "S. aureus", "bacilos gramnegativos"]
        if p.tiene("vih") or p.tiene("inmunosupresores"):
            out += ["Mycobacterium tuberculosis", "Cryptococcus spp."]
    elif p.foco == "osteoarticular":
        out = ["S. aureus (principal)", "Streptococcus pyogenes"]
        if 6 <= e < 48:
            out.append("Kingella kingae (6 meses-4 años)")
        if lactante_pequeno:
            out += ["SGB", "bacilos gramnegativos"]
        if p.tiene("asplenia"):
            out.append("Salmonella spp. (drepanocitosis)")
    elif p.foco == "piel_partes_blandas":
        out = ["S. aureus (incl. SARM-AC en abscesos)", "Streptococcus pyogenes"]
        if r.inmunocomprometido:
            out += ["P. aeruginosa (ectima gangrenoso)", "hongos"]
    return out


# ----------------------------------------------------------------------------
# Esquema empírico
# ----------------------------------------------------------------------------
def esquema_empirico(p: Paciente, r: PerfilRiesgo, grave: bool, choque: bool) -> Dict:
    e = p.edad_meses
    neonato = e < 1
    lactante_pequeno = e < 3
    farm: List[str] = []
    fundamentos: List[str] = []
    ambulatorio = False

    if p.foco == "neutropenia_febril" or (r.neutropenia and p.foco in ("sepsis_sin_foco", "nac")):
        if choque or r.riesgo_blee:
            farm = ["meropenem", "vancomicina"]
            fundamentos.append("Neutropenia febril con inestabilidad o riesgo BLEE: carbapenémico + glucopéptido.")
            if choque:
                farm.append("amikacina")
                fundamentos.append("En choque, considerar aminoglucósido para doble cobertura de gramnegativos.")
        else:
            farm = ["cefepime"]
            fundamentos.append("Neutropenia febril estable: monoterapia antipseudomónica (cefepime o pip/tazo).")
            if r.riesgo_sarm or p.tiene("cvc_portador"):
                farm.append("vancomicina")
                fundamentos.append("Agregar vancomicina solo si infección de CVC/piel, neumonía, colonización SARM o inestabilidad.")
    elif p.foco == "meningitis":
        if neonato:
            farm = ["ampicilina_snc", "cefotaxima_snc", "aciclovir"]
            fundamentos.append("<1 mes: cubrir SGB, E. coli y Listeria; aciclovir hasta descartar VHS.")
        elif lactante_pequeno:
            farm = ["ampicilina_snc", "ceftriaxona_snc", "vancomicina"]
            fundamentos.append("1-3 meses: cubrir Listeria/SGB tardío y neumococo resistente.")
        else:
            farm = ["ceftriaxona_snc", "vancomicina", "dexametasona"]
            fundamentos.append(">3 meses: ceftriaxona + vancomicina (neumococo no sensible); dexametasona antes o con la 1.ª dosis.")
        if p.tiene("derivacion_vp") or r.asociado_atencion_salud:
            farm = ["vancomicina", "meropenem_snc"]
            fundamentos.append("Portador de derivación / asociado a atención: vancomicina + betalactámico antipseudomónico.")
    elif p.foco == "cvc" or (p.foco == "sepsis_sin_foco" and r.asociado_atencion_salud and not neonato):
        farm = ["meropenem" if r.riesgo_blee else "cefepime", "vancomicina"]
        fundamentos.append("Infección asociada a atención/CVC: glucopéptido + antipseudomónico; "
                           "carbapenémico si colonización BLEE.")
    elif p.foco == "sepsis_sin_foco":
        if neonato:
            farm = ["ampicilina", "gentamicina"]
            fundamentos.append("Sepsis neonatal: ampicilina + gentamicina (evitar ceftriaxona <28 días).")
            if p.edad_meses < 0.75 or p.alteracion_conciencia:
                farm.append("aciclovir")
                fundamentos.append("<21 días o compromiso neurológico: aciclovir empírico.")
        elif lactante_pequeno:
            farm = ["ampicilina", "ceftriaxona"]
            fundamentos.append("1-3 meses: ceftriaxona ± ampicilina (Listeria/Enterococcus).")
        else:
            farm = ["ceftriaxona"]
            fundamentos.append("Sepsis comunitaria en niño previamente sano: cefalosporina de 3.ª generación.")
            if choque or r.riesgo_sarm:
                farm.append("vancomicina")
                fundamentos.append("Choque o riesgo SARM: agregar vancomicina.")
    elif p.foco == "nac":
        if neonato:
            farm = ["ampicilina", "gentamicina"]
            fundamentos.append("NAC neonatal: manejo como sepsis neonatal.")
        elif lactante_pequeno:
            farm = ["ceftriaxona"]
            fundamentos.append("1-3 meses febril: hospitalizar; si afebril con tos en accesos, considerar azitromicina (C. trachomatis / pertussis).")
        elif not grave and p.spo2 >= 92 and not r.inmunocomprometido:
            ambulatorio = True
            farm = ["amoxicilina"]
            fundamentos.append("NAC no grave en niño sano: amoxicilina a dosis altas (IDSA/PIDS).")
            if e >= 60:
                fundamentos.append("≥5 años con cuadro sugestivo de atípicos: considerar azitromicina.")
        else:
            if p.tiene("vacunacion_incompleta") or grave:
                farm = ["ceftriaxona"]
                fundamentos.append("NAC hospitalizada grave o vacunación incompleta: ceftriaxona.")
            else:
                farm = ["ampicilina"]
                fundamentos.append("NAC hospitalizada con vacunación completa: ampicilina IV.")
            if choque or r.riesgo_sarm:
                farm.append("vancomicina")
                fundamentos.append("Neumonía necrotizante/empiema, choque o riesgo SARM: agregar vancomicina (o clindamicina).")
        if r.riesgo_aspiracion and not neonato:
            farm = ["ampi_sulbactam"] + [f for f in farm if f == "vancomicina"]
            fundamentos.append("Riesgo de aspiración: ampicilina/sulbactam (anaerobios orales).")
        if r.inmunocomprometido and not r.neutropenia:
            farm = ["cefepime"] + [f for f in farm if f == "vancomicina"]
            fundamentos.append("Inmunocompromiso: cobertura antipseudomónica; considerar cotrimoxazol si sospecha de P. jirovecii.")
    elif p.foco == "itu":
        if neonato or e < 2:
            farm = ["ampicilina", "gentamicina"]
            fundamentos.append("<2 meses: ampicilina + gentamicina (Enterococcus y gramnegativos), descartar bacteriemia/meningitis.")
        elif r.riesgo_blee or choque:
            farm = ["meropenem" if choque else "amikacina"]
            fundamentos.append("Riesgo BLEE: amikacina (estable) o carbapenémico (grave). Ajustar por urocultivo.")
        elif grave or p.alteracion_conciencia:
            farm = ["ceftriaxona"]
            fundamentos.append("Pielonefritis con compromiso sistémico: ceftriaxona IV; pasar a VO según cultivo.")
        else:
            ambulatorio = True
            farm = ["cefixima"]
            fundamentos.append("Pielonefritis sin toxicidad y tolerando VO: cefalosporina oral; "
                               "ajustar según resistencia local (alta prevalencia de BLEE en Perú).")
    elif p.foco == "osteoarticular":
        if lactante_pequeno:
            farm = ["cefazolina", "cefotaxima"]
            fundamentos.append("<3 meses: cubrir SGB y gramnegativos además de S. aureus.")
        elif r.riesgo_sarm or grave:
            farm = ["vancomicina" if grave else "clindamicina"]
            fundamentos.append("Riesgo SARM: clindamicina (estable) o vancomicina (grave/bacteriemia).")
        else:
            farm = ["cefazolina"]
            fundamentos.append("Cefazolina: cubre S. aureus sensible y Kingella kingae (la clindamicina no cubre Kingella).")
    elif p.foco == "piel_partes_blandas":
        if grave or choque:
            farm = ["vancomicina", "pip_tazo", "clindamicina"]
            fundamentos.append("Sospecha de infección necrotizante: amplio espectro + clindamicina (antitoxina); valorar cirugía urgente.")
        elif r.riesgo_sarm:
            ambulatorio = True
            farm = ["tmp_smx"]
            fundamentos.append("Absceso con riesgo SARM-AC: drenaje + TMP-SMX o clindamicina.")
        else:
            ambulatorio = True
            farm = ["cefalexina"]
            fundamentos.append("Celulitis no purulenta: cefalexina.")

    dosis = [calcular_dosis(k, p.peso_kg) for k in dict.fromkeys(farm)]
    if choque:
        fundamentos.insert(0, "CHOQUE SÉPTICO: administrar antimicrobianos dentro de la 1.ª hora (Surviving Sepsis Campaign pediátrica 2020).")
    elif grave:
        fundamentos.insert(0, "Sepsis sin choque: antimicrobianos idealmente dentro de 3 h, tras evaluación y cultivos.")
    return {"ambulatorio": ambulatorio, "dosis": dosis, "fundamentos": fundamentos}


# ----------------------------------------------------------------------------
# Estudios sugeridos
# ----------------------------------------------------------------------------
def estudios(p: Paciente, r: PerfilRiesgo, grave: bool) -> List[str]:
    base = ["Hemocultivo (antes del antimicrobiano, sin retrasarlo >1 h en choque)",
            "Hemograma, PCR/procalcitonina"]
    if grave:
        base += ["Gasometría y lactato", "Perfil de coagulación (INR, fibrinógeno, dímero D)",
                 "Creatinina, bilirrubina, ALT, glucosa (completar Phoenix-8 / pSOFA)"]
    foco = {
        "nac": ["Radiografía de tórax (si hospitaliza o hipoxemia)", "Panel viral respiratorio",
                "Ecografía pleural si sospecha de derrame"],
        "sepsis_sin_foco": ["Examen de orina y urocultivo por sonda", "Punción lumbar si <3 meses o signos meníngeos"],
        "neutropenia_febril": ["Hemocultivo periférico y de cada lumen del CVC", "Urocultivo",
                               "Galactomanano / TC de tórax si fiebre >96 h"],
        "itu": ["Urocultivo por sonda o punción suprapúbica", "Ecografía renal y vesical"],
        "meningitis": ["Punción lumbar: citoquímico, Gram, cultivo, PCR multiplex (si no hay contraindicación)",
                       "Neuroimagen previa si focalidad, papiledema o inmunocompromiso"],
        "osteoarticular": ["Ecografía articular / RM", "Artrocentesis o aspirado óseo con cultivo y PCR para Kingella"],
        "piel_partes_blandas": ["Cultivo del drenaje", "Ecografía de partes blandas; CPK si sospecha necrotizante"],
        "cvc": ["Hemocultivos pareados (CVC y periférico) con tiempo diferencial de positividad",
                "Ecocardiograma si bacteriemia persistente por S. aureus"],
    }
    extras = foco.get(p.foco, [])
    if p.edad_meses < 1 and p.foco != "meningitis":
        extras.append("Punción lumbar (todo neonato con sospecha de sepsis)")
    if r.inmunocomprometido and p.foco != "neutropenia_febril":
        extras.append("Considerar búsqueda de oportunistas (P. jirovecii, CMV, hongos)")
    return base + extras


# ----------------------------------------------------------------------------
# Alertas por edad y sesgos cognitivos
# ----------------------------------------------------------------------------
def alertas_clinicas(p: Paciente, ph: ResultadoPhoenix) -> List[str]:
    g = grupo_etario(p.edad_meses)
    a = []
    if p.fc > g["fc_max"]:
        a.append(f"Taquicardia para la edad ({p.fc} > {g['fc_max']} lpm, {g['etiqueta']}).")
    if g["fc_min"] and p.fc < g["fc_min"]:
        a.append(f"Bradicardia para la edad ({p.fc} < {g['fc_min']} lpm): signo tardío/ominoso.")
    if p.fr > g["fr_max"]:
        a.append(f"Taquipnea para la edad ({p.fr} > {g['fr_max']} rpm).")
    if p.temp_c >= 38 and p.edad_meses < 3:
        a.append("Fiebre en <3 meses: alto riesgo de infección bacteriana grave.")
    if p.temp_c < 36:
        a.append("Hipotermia: puede indicar sepsis grave, sobre todo en neonatos.")
    if p.spo2 < 92:
        a.append(f"Hipoxemia (SpO2 {p.spo2:g} %).")
    if p.llenado_capilar_s > 2:
        a.append(f"Llenado capilar prolongado ({p.llenado_capilar_s:g} s).")
    if p.alteracion_conciencia or p.glasgow < 15:
        a.append("Alteración del estado de conciencia.")
    if ph.choque_septico:
        a.append("Criterios Phoenix de CHOQUE SÉPTICO.")
    elif ph.sepsis:
        a.append("Criterios Phoenix de SEPSIS (≥2 puntos).")
    return a


def sesgos_cognitivos(p: Paciente, r: PerfilRiesgo, ph: ResultadoPhoenix) -> List[str]:
    s = []
    if p.foco == "nac" and p.edad_meses < 24:
        s.append("Anclaje: en lactantes la mayoría de las NAC son virales; no toda condensación exige antibiótico de amplio espectro.")
    if not ph.sepsis and ph.faltantes:
        s.append("Cierre prematuro: Phoenix < 2 con laboratorios faltantes "
                 f"({', '.join(ph.faltantes[:4])}); un puntaje bajo por ausencia de datos no descarta disfunción orgánica.")
    if r.inmunocomprometido:
        s.append("Presentación atípica: el huésped inmunocomprometido puede no tener fiebre alta ni signos focales.")
    if p.edad_meses < 3:
        s.append("En lactantes pequeños la irritabilidad o el rechazo alimentario pueden ser el único signo de meningitis.")
    if p.tiene("atb_previo_30d"):
        s.append("Antibiótico previo: puede negativizar cultivos y seleccionar resistencia.")
    return s


def preguntas_docentes(p: Paciente, r: PerfilRiesgo, ph: ResultadoPhoenix) -> List[str]:
    q = [
        "¿Cuál es la representación del problema de este paciente en una sola frase?",
        "¿Qué dato cambiaría más su probabilidad pre-test de infección bacteriana grave?",
        f"¿Qué componente(s) del Phoenix explican el puntaje de {ph.total} y cuál es modificable en la 1.ª hora?",
    ]
    if r.inmunocomprometido:
        q.append("¿Qué patógenos oportunistas añade el estado inmunológico de este huésped?")
    if ph.faltantes:
        q.append("¿Qué laboratorio faltante solicitaría primero y por qué?")
    q.append("¿Cuándo y con qué datos desescalaría el esquema empírico (48-72 h)?")
    return q


# ----------------------------------------------------------------------------
# Escenario integrado
# ----------------------------------------------------------------------------
@dataclass
class Escenario:
    representacion: str
    grupo_etario: str
    phoenix: ResultadoPhoenix
    psofa: ResultadoScore
    perfil: PerfilRiesgo
    gravedad: str
    alertas: List[str]
    etiologias: List[str]
    estudios: List[str]
    esquema: Dict
    sesgos: List[str]
    preguntas: List[str]


def clasificar_gravedad(ph: ResultadoPhoenix, psofa: ResultadoScore) -> str:
    if ph.choque_septico:
        return "Choque séptico (Phoenix)"
    if ph.sepsis:
        return "Sepsis (Phoenix ≥ 2)"
    if psofa.total >= 2:
        return "Disfunción orgánica por pSOFA ≥ 2 (Phoenix < 2): vigilar"
    return "Infección sin disfunción orgánica por criterios actuales"


def representacion_problema(p: Paciente, ph: ResultadoPhoenix, r: PerfilRiesgo) -> str:
    como = [COMORBILIDADES[c].split(" (")[0].lower() for c in p.comorbilidades if c in COMORBILIDADES]
    antecedentes = f", con {', '.join(como)}" if como else ", previamente sano/a"
    comp = [f"{k.lower()} {v}" for k, v in ph.componentes.items() if v]
    disf = f"; Phoenix {ph.total} ({', '.join(comp)})" if comp else "; Phoenix 0"
    sexo = "" if p.sexo == "No especificado" else f" de sexo {p.sexo.lower()}"
    return (f"Paciente de {describir_edad(p.edad_meses)}{sexo}{antecedentes}, "
            f"con sospecha de {FOCOS[p.foco][0].lower() + FOCOS[p.foco][1:]}{disf}"
            + (". Cumple criterios de choque séptico." if ph.choque_septico
               else ". Cumple criterios de sepsis." if ph.sepsis else "."))


def generar_escenario(p: Paciente, o2_bajo_flujo_cuenta: bool = False) -> Escenario:
    ph = calcular_phoenix(p, o2_bajo_flujo_cuenta=o2_bajo_flujo_cuenta)
    ps = calcular_psofa(p)
    r = perfil_riesgo(p)
    grave = ph.sepsis or ps.total >= 2
    return Escenario(
        representacion=representacion_problema(p, ph, r),
        grupo_etario=grupo_etario(p.edad_meses)["etiqueta"],
        phoenix=ph, psofa=ps, perfil=r,
        gravedad=clasificar_gravedad(ph, ps),
        alertas=alertas_clinicas(p, ph),
        etiologias=etiologias(p, r),
        estudios=estudios(p, r, grave),
        esquema=esquema_empirico(p, r, grave, ph.choque_septico),
        sesgos=sesgos_cognitivos(p, r, ph),
        preguntas=preguntas_docentes(p, r, ph),
    )


# ----------------------------------------------------------------------------
# Escenarios contrafactuales "¿y si...?"
# ----------------------------------------------------------------------------
def escenarios_alternativos(p: Paciente) -> List[Dict]:
    """Varía una dimensión del caso y recalcula para mostrar su impacto."""
    variantes = []

    def agregar(titulo: str, q: Paciente, explicacion: str):
        esc = generar_escenario(q)
        variantes.append({
            "titulo": titulo,
            "explicacion": explicacion,
            "phoenix": esc.phoenix.total,
            "gravedad": esc.gravedad,
            "esquema": ", ".join(d["farmaco"] for d in esc.esquema["dosis"]) or "—",
        })

    if (p.lactato or 0) < 5:
        agregar("¿Y si el lactato fuera 5.5 mmol/L?", replace(p, lactato=5.5),
                "El lactato ≥5 suma 1 punto cardiovascular y, con Phoenix ≥2, define choque séptico.")
    if p.soporte_resp != "vmi":
        agregar("¿Y si requiriera intubación con SpO2 88 % y FiO2 0.5?",
                replace(p, soporte_resp="vmi", spo2=88, fio2=0.5, pao2=None),
                "Con VMI, SpO2:FiO2 <220 suma 2 puntos respiratorios.")
    if p.edad_meses >= 1:
        agregar("¿Y si fuera un neonato de 10 días (3.2 kg)?", replace(p, edad_meses=0.33, peso_kg=3.2),
                "La edad cambia las etiologías (SGB, Listeria), los umbrales de PAM y el esquema (evitar ceftriaxona).")
    if "cancer_quimio" not in p.comorbilidades:
        agregar("¿Y si estuviera en quimioterapia con RAN 200/mm³?",
                replace(p, comorbilidades=p.comorbilidades + ["cancer_quimio"], anc=200),
                "La neutropenia convierte el caso en neutropenia febril: cobertura antipseudomónica.")
    if not p.vasoactivos:
        agregar("¿Y si requiriera norepinefrina 0.1 µg/kg/min?",
                replace(p, vasoactivos={"norepinefrina": 0.1}),
                "Un vasoactivo suma 1 punto cardiovascular Phoenix y 3 en pSOFA.")
    return variantes
