# ==============================================================================
# RAZONAMIENTO CLÍNICO EN INFECTOLOGÍA PEDIÁTRICA
# Phoenix Sepsis Score · pSOFA · escenarios de razonamiento · PubMed · registro
# ==============================================================================
from __future__ import annotations

import hmac
from datetime import datetime

import pandas as pd
import streamlit as st

from core.almacenamiento import obtener_almacen
from core.casos import CASOS
from core.models import (COMORBILIDADES, FACTORES_EPIDEMIOLOGICOS, FOCOS,
                         SOPORTE_RESP, VASOACTIVOS, Paciente)
from core.pubmed import TERMINOS_EXTRA, buscar_pubmed, construir_query, vincular_evidencia
from core.razonamiento import describir_edad, escenarios_alternativos, generar_escenario

st.set_page_config(page_title="Razonamiento Clínico Pediátrico", page_icon="🩺",
                   layout="wide", initial_sidebar_state="expanded")


# ------------------------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------------------------
def secreto(seccion: str, clave: str, defecto=None):
    try:
        return st.secrets.get(seccion, {}).get(clave, defecto)
    except Exception:
        return defecto


@st.cache_resource(show_spinner=False)
def almacen():
    try:
        s = st.secrets
        _ = s.get("storage")  # fuerza lectura; lanza si no hay secrets.toml
    except Exception:
        s = None
    return obtener_almacen(s)


@st.cache_data(ttl=3600, show_spinner=False)
def pubmed_cache(query: str, email: str, api_key: str | None, n: int):
    return buscar_pubmed(query, email, api_key, n)


VASO_CON_DOSIS = ("dopamina", "epinefrina", "norepinefrina")
DEFAULTS = dict(
    codigo="", evaluador="", edad_valor=18, edad_unidad="meses", peso_kg=11.0, sexo="No especificado",
    foco="nac", comorbilidades=[], factores=[], notas="",
    temp_c=38.5, fc=140, fr=40, pas=90, pad=55, llenado_capilar_s=2.0, alteracion_conciencia=False,
    spo2=95.0, fio2=0.21, pao2=None, soporte_resp="ninguno", vasoactivos=[], lactato=None,
    plaquetas=None, inr=None, dimero_d=None, fibrinogeno=None, glasgow=15, pupilas_fijas=False,
    glucosa=None, anc=None, alc=None, creatinina=None, bilirrubina=None, alt=None,
    **{f"dosis_{d}": 0.0 for d in VASO_CON_DOSIS},
)
for k, v in DEFAULTS.items():
    st.session_state.setdefault(f"f_{k}", v)


def cargar_caso(nombre: str):
    for k, v in {**DEFAULTS, **CASOS[nombre]}.items():
        st.session_state[f"f_{k}"] = v
    st.session_state["f_codigo"] = f"DEMO-{datetime.now():%H%M%S}"


def reiniciar():
    for k, v in DEFAULTS.items():
        st.session_state[f"f_{k}"] = v


def edad_en_meses(valor: float, unidad: str) -> float:
    return {"días": valor / 30.4, "meses": valor, "años": valor * 12}[unidad]


# ------------------------------------------------------------------------------
# Barra lateral
# ------------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    caso = st.selectbox("Casos de ejemplo (docencia)", ["—"] + list(CASOS), key="caso_demo")
    c1, c2 = st.columns(2)
    c1.button("Cargar caso", disabled=caso == "—", on_click=cargar_caso, args=(caso,),
              width="stretch")
    c2.button("Limpiar", on_click=reiniciar, width="stretch")

    st.divider()
    o2_cuenta = st.toggle(
        "Contar O2 bajo flujo como soporte (Phoenix resp.)", value=False,
        help="La implementación oficial (paquete `phoenix`) considera soporte respiratorio a "
             "alto flujo, VNI o VMI. Active para análisis de sensibilidad en contextos con "
             "acceso limitado a gasometría/alto flujo.")
    email_ncbi = st.text_input("Correo para NCBI Entrez",
                               value=secreto("ncbi", "email", ""),
                               help="Requerido por NCBI para usar la API de PubMed.")
    st.divider()
    almac, aviso_almac = almacen()
    st.caption(f"💾 Almacenamiento: **{almac.nombre}**")
    if aviso_almac:
        st.warning(aviso_almac)
    st.caption("⚠️ Herramienta educativa. No sustituye el juicio clínico ni las guías institucionales. "
               "No registre nombres ni documentos de identidad.")

st.title("🩺 Razonamiento Clínico en Infectología Pediátrica")
st.caption("Phoenix Sepsis Score (JAMA 2024) · pSOFA · escenarios de razonamiento por edad y comorbilidad · "
           "evidencia PubMed reciente · registro en Drive")

tab_ing, tab_eval, tab_esc, tab_pub, tab_reg = st.tabs(
    ["1 · Ingreso del paciente", "2 · Phoenix / pSOFA", "3 · Escenario de razonamiento",
     "4 · Evidencia PubMed", "5 · Registro"])

# ------------------------------------------------------------------------------
# 1. INGRESO DEL PACIENTE
# ------------------------------------------------------------------------------
with tab_ing:
    st.subheader("Identificación")
    a, b, c = st.columns([2, 2, 1])
    a.text_input("Código de registro / ID de ficha *", key="f_codigo",
                 placeholder="Ej. PED-2026-0042", help="Código anonimizado. Obligatorio para guardar.")
    b.text_input("Evaluador (opcional)", key="f_evaluador")
    c.selectbox("Sexo", ["No especificado", "Femenino", "Masculino"], key="f_sexo")

    st.subheader("Datos demográficos y contexto clínico")
    a, b, c, d = st.columns(4)
    a.number_input("Edad", min_value=0, max_value=216, step=1, key="f_edad_valor")
    b.selectbox("Unidad", ["días", "meses", "años"], key="f_edad_unidad")
    c.number_input("Peso (kg)", min_value=0.5, max_value=150.0, step=0.1, key="f_peso_kg")
    d.selectbox("Foco infeccioso sospechado", list(FOCOS), format_func=FOCOS.get, key="f_foco")
    edad_m = edad_en_meses(st.session_state.f_edad_valor, st.session_state.f_edad_unidad)
    if edad_m > 216:
        st.error("Edad > 18 años: los puntajes pediátricos no aplican.")
    else:
        st.caption(f"Edad calculada: {describir_edad(edad_m)} ({edad_m:.1f} meses)")

    a, b = st.columns(2)
    a.multiselect("Comorbilidades", list(COMORBILIDADES), format_func=COMORBILIDADES.get,
                  key="f_comorbilidades")
    b.multiselect("Factores epidemiológicos / de resistencia", list(FACTORES_EPIDEMIOLOGICOS),
                  format_func=FACTORES_EPIDEMIOLOGICOS.get, key="f_factores")

    st.subheader("Signos vitales y examen")
    a, b, c, d, e = st.columns(5)
    a.number_input("Temperatura (°C)", 33.0, 43.0, step=0.1, key="f_temp_c")
    b.number_input("FC (lpm)", 30, 260, key="f_fc")
    c.number_input("FR (rpm)", 5, 120, key="f_fr")
    d.number_input("PAS (mmHg)", 20, 220, key="f_pas")
    e.number_input("PAD (mmHg)", 10, 150, key="f_pad")
    a, b, c = st.columns(3)
    pam = round((st.session_state.f_pas + 2 * st.session_state.f_pad) / 3, 1)
    a.metric("PAM calculada", f"{pam} mmHg")
    b.number_input("Llenado capilar (s)", 0.0, 10.0, step=0.5, key="f_llenado_capilar_s")
    c.checkbox("Alteración de conciencia / letargia", key="f_alteracion_conciencia")

    st.subheader("Variables Phoenix / pSOFA")
    st.caption("Deje en blanco los laboratorios no disponibles: puntúan 0 y se señalan como faltantes.")
    col_r, col_c, col_k = st.columns(3)
    with col_r:
        st.markdown("**Respiratorio**")
        st.selectbox("Soporte respiratorio", list(SOPORTE_RESP), format_func=SOPORTE_RESP.get,
                     key="f_soporte_resp")
        st.number_input("SpO2 (%)", 50.0, 100.0, step=0.5, key="f_spo2")
        st.number_input("FiO2 (0.21-1.0)", 0.21, 1.0, step=0.01, key="f_fio2")
        st.number_input("PaO2 (mmHg) — opcional", 10.0, 600.0, key="f_pao2")
    with col_c:
        st.markdown("**Cardiovascular**")
        st.multiselect("Vasoactivos en infusión", list(VASOACTIVOS), format_func=VASOACTIVOS.get,
                       key="f_vasoactivos")
        for dr in VASO_CON_DOSIS:
            if dr in st.session_state.f_vasoactivos:
                st.number_input(f"Dosis {VASOACTIVOS[dr].split(' ')[0].lower()} (µg/kg/min)",
                                0.0, 50.0, step=0.01, key=f"f_dosis_{dr}")
        st.number_input("Lactato (mmol/L)", 0.0, 30.0, step=0.1, key="f_lactato")
    with col_k:
        st.markdown("**Coagulación**")
        st.number_input("Plaquetas (×10³/µL)", 0.0, 1500.0, key="f_plaquetas")
        st.number_input("INR", 0.5, 15.0, step=0.1, key="f_inr")
        st.number_input("Dímero D (mg/L FEU)", 0.0, 50.0, step=0.1, key="f_dimero_d")
        st.number_input("Fibrinógeno (mg/dL)", 0.0, 1500.0, key="f_fibrinogeno")

    col_n, col_x = st.columns([1, 2])
    with col_n:
        st.markdown("**Neurológico**")
        st.slider("Escala de Glasgow", 3, 15, key="f_glasgow")
        st.checkbox("Pupilas fijas bilaterales", key="f_pupilas_fijas")
    with col_x:
        st.markdown("**Phoenix-8 / pSOFA (endocrino, inmunológico, renal, hepático)**")
        a, b, c = st.columns(3)
        a.number_input("Glucosa (mg/dL)", 0.0, 1500.0, key="f_glucosa")
        a.number_input("Creatinina (mg/dL)", 0.0, 20.0, step=0.1, key="f_creatinina")
        b.number_input("RAN (/mm³)", 0.0, 100000.0, key="f_anc")
        b.number_input("RAL (/mm³)", 0.0, 100000.0, key="f_alc")
        c.number_input("Bilirrubina total (mg/dL)", 0.0, 60.0, step=0.1, key="f_bilirrubina")
        c.number_input("ALT (UI/L)", 0.0, 10000.0, key="f_alt")

    st.text_area("Notas clínicas", key="f_notas", placeholder="Hallazgos relevantes del examen…")

# ------------------------------------------------------------------------------
# Construcción del paciente y cálculo (reactivo)
# ------------------------------------------------------------------------------
S = st.session_state
vaso = {d: (S[f"f_dosis_{d}"] if d in VASO_CON_DOSIS else 0.0) for d in S.f_vasoactivos}
paciente = Paciente(
    codigo_registro=S.f_codigo.strip(), evaluador=S.f_evaluador.strip(),
    edad_meses=round(min(edad_m, 216), 2), sexo=S.f_sexo, peso_kg=S.f_peso_kg,
    foco=S.f_foco, comorbilidades=list(S.f_comorbilidades), factores=list(S.f_factores),
    notas=S.f_notas, temp_c=S.f_temp_c, fc=S.f_fc, fr=S.f_fr, pas=S.f_pas, pad=S.f_pad,
    llenado_capilar_s=S.f_llenado_capilar_s, alteracion_conciencia=S.f_alteracion_conciencia,
    spo2=S.f_spo2, fio2=S.f_fio2, pao2=S.f_pao2, soporte_resp=S.f_soporte_resp,
    vasoactivos=vaso, lactato=S.f_lactato, plaquetas=S.f_plaquetas, inr=S.f_inr,
    dimero_d=S.f_dimero_d, fibrinogeno=S.f_fibrinogeno, glasgow=S.f_glasgow,
    pupilas_fijas=S.f_pupilas_fijas, glucosa=S.f_glucosa, anc=S.f_anc, alc=S.f_alc,
    creatinina=S.f_creatinina, bilirrubina=S.f_bilirrubina, alt=S.f_alt,
)
esc = generar_escenario(paciente, o2_bajo_flujo_cuenta=o2_cuenta)
ph, ps = esc.phoenix, esc.psofa

# ------------------------------------------------------------------------------
# 2. PHOENIX / pSOFA
# ------------------------------------------------------------------------------
with tab_eval:
    if ph.choque_septico:
        st.error(f"🚨 **{esc.gravedad}** — iniciar reanimación, vasoactivos si refractario y antimicrobianos en la 1.ª hora.")
    elif ph.sepsis:
        st.warning(f"⚠️ **{esc.gravedad}** — hemocultivos y antimicrobianos precoces.")
    else:
        st.info(f"ℹ️ **{esc.gravedad}**")

    m = st.columns(4)
    m[0].metric("Phoenix Sepsis Score", f"{ph.total} / 13")
    m[1].metric("Phoenix-8", f"{ph.phoenix8} / 20")
    m[2].metric("pSOFA", f"{ps.total} / 24")
    m[3].metric("Grupo etario", esc.grupo_etario.split(" (")[0])

    a, b = st.columns(2)
    with a:
        st.markdown("##### Phoenix: desglose")
        st.dataframe(pd.DataFrame({
            "Sistema": list(ph.componentes8),
            "Puntos": list(ph.componentes8.values()),
            "Detalle": [ph.detalle.get(k, "Phoenix-8") for k in ph.componentes8],
        }), hide_index=True, width="stretch")
        st.caption("Sepsis = infección sospechada + Phoenix ≥2. Choque séptico = sepsis + ≥1 punto cardiovascular. "
                   "Phoenix-8 agrega endocrino, inmunológico, renal y hepático (uso en investigación).")
    with b:
        st.markdown("##### pSOFA: desglose")
        st.dataframe(pd.DataFrame({
            "Sistema": list(ps.componentes), "Puntos": list(ps.componentes.values()),
            "Detalle": [ps.detalle[k] for k in ps.componentes],
        }), hide_index=True, width="stretch")
        st.caption("pSOFA ≥2 (o aumento ≥2 respecto a la basal) sugiere disfunción orgánica asociada a infección.")

    faltan = sorted(set(ph.faltantes + ps.faltantes))
    if faltan:
        st.warning("Datos faltantes (puntuados como normales): " + ", ".join(faltan))

# ------------------------------------------------------------------------------
# 3. ESCENARIO DE RAZONAMIENTO
# ------------------------------------------------------------------------------
with tab_esc:
    st.markdown("#### 🧠 Representación del problema")
    st.info(esc.representacion)

    a, b = st.columns(2)
    with a:
        st.markdown("#### 🚩 Banderas rojas (ajustadas por edad)")
        for al in esc.alertas or ["Sin alertas por signos vitales."]:
            st.markdown(f"- {al}")
        if esc.perfil.motivos:
            st.markdown("#### 🛡️ Perfil del huésped")
            for mo in esc.perfil.motivos:
                st.markdown(f"- {mo}")
        st.markdown("#### 🦠 Etiologías probables")
        for et in esc.etiologias:
            st.markdown(f"- {et}")
        st.markdown("#### 🔬 Estudios sugeridos")
        for es in esc.estudios:
            st.markdown(f"- {es}")
    with b:
        esq = esc.esquema
        st.markdown("#### 💊 Esquema empírico orientativo"
                    + (" (manejo ambulatorio posible)" if esq["ambulatorio"] else ""))
        if esq["dosis"]:
            st.dataframe(pd.DataFrame([{
                "Fármaco": d["farmaco"], "Vía": d["via"], "mg/kg/día": d["mg_kg_dia"],
                "Dosis": f"{d['mg_dosis']:g} mg {d['intervalo']}",
                "Total/día": f"{d['mg_dia']:g} mg" + (" (tope)" if d["tope_aplicado"] else ""),
            } for d in esq["dosis"]]), hide_index=True, width="stretch")
            for d in esq["dosis"]:
                if d["nota"]:
                    st.caption(f"• {d['farmaco']}: {d['nota']}")
        st.markdown("**Fundamento**")
        for f in esq["fundamentos"]:
            st.markdown(f"- {f}")
        st.caption("Adaptar a la epidemiología y resistencia local; reevaluar a las 48-72 h con cultivos.")

    st.divider()
    a, b = st.columns(2)
    with a:
        st.markdown("#### ⚖️ Sesgos cognitivos a vigilar")
        for s_ in esc.sesgos or ["—"]:
            st.markdown(f"- {s_}")
    with b:
        st.markdown("#### ❓ Preguntas de razonamiento")
        for i, q in enumerate(esc.preguntas, 1):
            st.markdown(f"{i}. {q}")

    st.markdown("#### 🔀 Escenarios alternativos: ¿y si…?")
    st.caption("Cada escenario modifica una sola variable del caso y recalcula puntajes y esquema.")
    alt = escenarios_alternativos(paciente)
    st.dataframe(pd.DataFrame([{
        "Escenario": v["titulo"], "Phoenix": f"{ph.total} → {v['phoenix']}",
        "Clasificación": v["gravedad"], "Esquema": v["esquema"], "Aprendizaje": v["explicacion"],
    } for v in alt]), hide_index=True, width="stretch")

# ------------------------------------------------------------------------------
# 4. EVIDENCIA PUBMED
# ------------------------------------------------------------------------------
with tab_pub:
    a, b, c = st.columns([1, 1, 2])
    meses = a.slider("Ventana (meses)", 1, 12, 2)
    n_res = b.slider("Máx. artículos", 5, 30, 10)
    extras = c.multiselect("Enfoque adicional", list(TERMINOS_EXTRA),
                           format_func={"phoenix": "Disfunción orgánica / Phoenix",
                                        "resistencia": "Resistencia / stewardship"}.get)
    query = construir_query(paciente.foco, meses, extras)
    with st.expander("Ver query PubMed"):
        st.code(query, language="text")
    if st.button("🔎 Buscar evidencia reciente", type="primary"):
        if "@" not in email_ncbi:
            st.error("Ingrese un correo válido en la barra lateral (requisito de NCBI).")
        else:
            with st.spinner("Consultando NCBI Entrez…"):
                df, err = pubmed_cache(query, email_ncbi, secreto("ncbi", "api_key"), n_res)
            if err:
                st.error(f"No se pudo consultar PubMed: {err}")
            elif df.empty:
                st.info("Sin publicaciones en la ventana seleccionada. Amplíe el rango de meses.")
            else:
                df = vincular_evidencia(df, [d["farmaco"] for d in esc.esquema["dosis"]])
                st.success(f"{len(df)} artículos. Resaltados los que mencionan fármacos del esquema sugerido.")
                for _, r in df.iterrows():
                    marca = f" · 💊 {r['Menciona']}" if r.get("Menciona") else ""
                    with st.expander(f"{r['Titulo']} — {r['Revista']} {r['Anio']}{marca}"):
                        st.caption(f"PMID {r['PMID']} · {r['Tipo']}")
                        st.write(r["Resumen"][:1200] + ("…" if len(r["Resumen"]) > 1200 else "")
                                 if r["Resumen"] else "Sin resumen disponible.")
                        st.markdown(f"[Abrir en PubMed]({r['URL']})"
                                    + (f" · [DOI](https://doi.org/{r['DOI']})" if r["DOI"] else ""))
                st.download_button("⬇️ Descargar referencias (CSV)", df.to_csv(index=False).encode("utf-8"),
                                   f"pubmed_{paciente.foco}_{datetime.now():%Y%m%d}.csv", "text/csv")

# ------------------------------------------------------------------------------
# 5. REGISTRO
# ------------------------------------------------------------------------------
def registro_plano() -> dict:
    d = paciente.to_dict()
    d["vasoactivos"] = "; ".join(f"{k}:{v:g}" for k, v in paciente.vasoactivos.items())
    d["comorbilidades"] = "; ".join(paciente.comorbilidades)
    d["factores"] = "; ".join(paciente.factores)
    d.update({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pam": paciente.pam,
        "phoenix_total": ph.total,
        **{f"phoenix_{k.lower()}": v for k, v in ph.componentes8.items()},
        "phoenix8_total": ph.phoenix8,
        "psofa_total": ps.total,
        **{f"psofa_{k.lower()}": v for k, v in ps.componentes.items()},
        "sepsis_phoenix": ph.sepsis,
        "choque_septico_phoenix": ph.choque_septico,
        "clasificacion": esc.gravedad,
        "esquema_sugerido": "; ".join(f"{x['farmaco']} {x['mg_dosis']:g} mg {x['intervalo']}"
                                      for x in esc.esquema["dosis"]),
        "o2_bajo_flujo_cuenta": o2_cuenta,
    })
    orden = ["timestamp", "codigo_registro", "evaluador"]
    return {k: d[k] for k in orden + [k for k in d if k not in orden]}


with tab_reg:
    st.markdown(f"**Destino:** {almac.nombre}")
    reg = registro_plano()
    with st.expander("Vista previa del registro"):
        st.json(reg, expanded=False)
    if st.button("💾 Guardar evaluación", type="primary"):
        if not paciente.codigo_registro:
            st.error("El **código de registro** es obligatorio (pestaña 1).")
        else:
            try:
                with st.spinner("Guardando…"):
                    almac.guardar(reg)
                st.success(f"Evaluación {paciente.codigo_registro} guardada en {almac.nombre}.")
            except Exception as exc:
                st.error(f"Error al guardar: {exc}")
                st.download_button("⬇️ Descargar este registro (CSV)",
                                   pd.DataFrame([reg]).to_csv(index=False).encode("utf-8"),
                                   f"{paciente.codigo_registro}.csv", "text/csv")

    st.divider()
    st.markdown("##### 🔒 Histórico consolidado (acceso restringido)")
    clave_admin = secreto("admin", "password")
    if not clave_admin:
        st.info("El histórico está deshabilitado. Configure `[admin] password` en los secrets para habilitarlo.")
    elif not st.session_state.get("admin_ok"):
        intentos = st.session_state.get("admin_intentos", 0)
        if intentos >= 5:
            st.error("Demasiados intentos fallidos. Recargue la página para reintentar.")
        else:
            with st.form("login_admin", clear_on_submit=True):
                pwd = st.text_input("Contraseña de administrador", type="password")
                if st.form_submit_button("Ingresar"):
                    if hmac.compare_digest(pwd.encode(), str(clave_admin).encode()):
                        st.session_state["admin_ok"] = True
                        st.session_state["admin_intentos"] = 0
                        st.rerun()
                    else:
                        st.session_state["admin_intentos"] = intentos + 1
                        st.error("Contraseña incorrecta.")
            st.caption("Solo el administrador puede ver y descargar los registros guardados.")
    else:
        if st.button("Cerrar sesión de administrador"):
            st.session_state["admin_ok"] = False
            st.rerun()
        try:
            hist = almac.leer()
        except Exception as exc:
            hist = pd.DataFrame()
            st.error(f"No se pudo leer el histórico: {exc}")
        if hist.empty:
            st.info("Aún no hay evaluaciones guardadas.")
        else:
            cols = [c for c in ["timestamp", "codigo_registro", "edad_meses", "foco", "phoenix_total",
                                "psofa_total", "clasificacion", "esquema_sugerido"] if c in hist.columns]
            st.dataframe(hist[cols], hide_index=True, width="stretch")
            st.download_button("⬇️ Descargar histórico (CSV)", hist.to_csv(index=False).encode("utf-8"),
                               "registro_evaluaciones.csv", "text/csv")
