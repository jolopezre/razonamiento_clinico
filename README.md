# Razonamiento Clínico en Infectología Pediátrica

App Streamlit educativa: ingreso de pacientes, **Phoenix Sepsis Score** (+ Phoenix-8),
**pSOFA**, escenarios de razonamiento ajustados por **edad y comorbilidad**, evidencia
reciente de **PubMed** y registro en **CSV de Google Drive**.

## Estructura
```
app.py                    # interfaz (5 pestañas)
core/models.py            # modelo Paciente, catálogos (focos, comorbilidades…)
core/scores.py            # Phoenix / Phoenix-8 / pSOFA (cortes por edad)
core/razonamiento.py      # motor de escenarios + "¿y si…?"
core/antimicrobianos.py   # dosis mg/kg/día con tope máximo
core/pubmed.py            # Entrez: query MeSH, reintentos, vínculo con esquema
core/almacenamiento.py    # Drive CSV / Google Sheets / CSV local
core/casos.py             # casos docentes precargados
tests/                    # 57 pruebas (pytest)
```

## Ejecutar
```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
streamlit run app.py
```

## Guardar en un CSV de Google Drive
1. Google Cloud Console → crear proyecto → habilitar **Google Drive API** (y Sheets API si usa `sheets`).
2. Crear una **cuenta de servicio** → Claves → JSON.
3. En su Drive, crear/subir `registro_evaluaciones.csv` (puede estar vacío) y **compartirlo como Editor**
   con el `client_email` de la cuenta de servicio.
4. Streamlit Cloud → *App settings → Secrets*: pegar `.streamlit/secrets.toml.example` completado.

Sin secretos, la app guarda en un CSV local (se pierde al reiniciar en Streamlit Cloud) y ofrece descarga.

## Referencias
- Schlapbach LJ, et al. JAMA 2024;331:665-674 · Sanchez-Pinto LN, et al. JAMA 2024;331:675-686
- Matics TJ, Sanchez-Pinto LN. JAMA Pediatr 2017;171:e172352
- Goldstein B, et al. Pediatr Crit Care Med 2005;6:2-8 (signos vitales por edad)
- Weiss SL, et al. Surviving Sepsis Campaign pediátrica. Pediatr Crit Care Med 2020

> Herramienta educativa. No reemplaza el juicio clínico ni las guías institucionales.
