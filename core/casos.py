"""Casos de ejemplo para docencia (valores de los widgets del formulario)."""

CASOS = {
    "Lactante con NAC complicada y choque": dict(
        edad_valor=14, edad_unidad="meses", peso_kg=10.2, sexo="Femenino", foco="nac",
        comorbilidades=["cardiopatia"], factores=["atb_previo_30d"],
        temp_c=39.1, fc=165, fr=56, pas=70, pad=40, llenado_capilar_s=4.0, alteracion_conciencia=False,
        spo2=89.0, fio2=0.5, pao2=None, soporte_resp="vmi",
        vasoactivos=["epinefrina"], dosis_epinefrina=0.08, lactato=5.4,
        plaquetas=85.0, inr=1.4, dimero_d=None, fibrinogeno=180.0,
        glasgow=12, pupilas_fijas=False, creatinina=0.5, bilirrubina=0.9, glucosa=160.0, anc=9000.0, alc=1500.0, alt=40.0,
    ),
    "Neonato de 10 días con fiebre sin foco": dict(
        edad_valor=10, edad_unidad="días", peso_kg=3.3, sexo="Masculino", foco="sepsis_sin_foco",
        comorbilidades=[], factores=[],
        temp_c=38.4, fc=190, fr=62, pas=60, pad=35, llenado_capilar_s=3.0, alteracion_conciencia=True,
        spo2=96.0, fio2=0.21, pao2=None, soporte_resp="ninguno",
        vasoactivos=[], lactato=3.1, plaquetas=140.0, inr=None, dimero_d=None, fibrinogeno=None,
        glasgow=14, pupilas_fijas=False, creatinina=None, bilirrubina=None, glucosa=None, anc=None, alc=None, alt=None,
    ),
    "Escolar con LLA y neutropenia febril": dict(
        edad_valor=7, edad_unidad="años", peso_kg=22.0, sexo="Masculino", foco="neutropenia_febril",
        comorbilidades=["cancer_quimio", "cvc_portador"], factores=["hosp_reciente_90d"],
        temp_c=38.8, fc=138, fr=24, pas=92, pad=55, llenado_capilar_s=2.0, alteracion_conciencia=False,
        spo2=97.0, fio2=0.21, pao2=None, soporte_resp="ninguno",
        vasoactivos=[], lactato=1.8, plaquetas=45.0, inr=1.1, dimero_d=None, fibrinogeno=250.0,
        glasgow=15, pupilas_fijas=False, creatinina=0.5, bilirrubina=0.6, glucosa=110.0, anc=200.0, alc=400.0, alt=35.0,
    ),
}
