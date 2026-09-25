"""Persistencia de evaluaciones: CSV en Google Drive, Google Sheets o CSV local.

Configuración en `.streamlit/secrets.toml` (ver `secrets.toml.example`):

    [storage]
    backend = "drive_csv"        # "drive_csv" | "sheets" | "local"
    drive_file_id = "1AbC..."    # CSV existente en Drive, compartido con la cuenta de servicio (Editor)
    sheet_key = "1XyZ..."        # para backend "sheets"
    worksheet = "registros"

    [gcp_service_account]
    type = "service_account"
    ...

Nota: las cuentas de servicio no tienen cuota propia en "Mi unidad", por eso el
CSV debe crearlo el usuario y compartirlo; la app solo lo actualiza.
"""
from __future__ import annotations

import io
import os
from typing import Mapping, Optional, Tuple

import pandas as pd

SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
RUTA_LOCAL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "registros.csv")


def _credenciales(secrets: Mapping):
    from google.oauth2.service_account import Credentials
    return Credentials.from_service_account_info(dict(secrets["gcp_service_account"]), scopes=SCOPES)


def _unir(df_existente: pd.DataFrame, registro: dict) -> pd.DataFrame:
    nuevo = pd.DataFrame([registro])
    if df_existente.empty:
        return nuevo
    return pd.concat([df_existente, nuevo], ignore_index=True)


# ----------------------------------------------------------------------------
class AlmacenLocal:
    nombre = "CSV local (efímero en Streamlit Cloud)"

    def __init__(self, ruta: Optional[str] = None):
        self.ruta = ruta or RUTA_LOCAL

    def leer(self) -> pd.DataFrame:
        return pd.read_csv(self.ruta) if os.path.exists(self.ruta) else pd.DataFrame()

    def guardar(self, registro: dict) -> None:
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        _unir(self.leer(), registro).to_csv(self.ruta, index=False, encoding="utf-8")


class AlmacenDriveCSV:
    nombre = "CSV en Google Drive"
    API = "https://www.googleapis.com"

    def __init__(self, secrets: Mapping):
        from google.auth.transport.requests import AuthorizedSession
        self.file_id = secrets["storage"]["drive_file_id"]
        self.sesion = AuthorizedSession(_credenciales(secrets))

    def leer(self) -> pd.DataFrame:
        r = self.sesion.get(f"{self.API}/drive/v3/files/{self.file_id}",
                            params={"alt": "media", "supportsAllDrives": "true"}, timeout=30)
        r.raise_for_status()
        texto = r.content.decode("utf-8-sig").strip()
        return pd.read_csv(io.StringIO(texto)) if texto else pd.DataFrame()

    def guardar(self, registro: dict) -> None:
        df = _unir(self.leer(), registro)
        r = self.sesion.patch(
            f"{self.API}/upload/drive/v3/files/{self.file_id}",
            params={"uploadType": "media", "supportsAllDrives": "true"},
            data=df.to_csv(index=False).encode("utf-8"),
            headers={"Content-Type": "text/csv"}, timeout=60,
        )
        r.raise_for_status()


class AlmacenSheets:
    nombre = "Google Sheets"

    def __init__(self, secrets: Mapping):
        import gspread
        cliente = gspread.authorize(_credenciales(secrets))
        libro = cliente.open_by_key(secrets["storage"]["sheet_key"])
        nombre_hoja = secrets["storage"].get("worksheet", "registros")
        try:
            self.hoja = libro.worksheet(nombre_hoja)
        except gspread.WorksheetNotFound:
            self.hoja = libro.add_worksheet(nombre_hoja, rows=1000, cols=80)

    def leer(self) -> pd.DataFrame:
        return pd.DataFrame(self.hoja.get_all_records())

    def guardar(self, registro: dict) -> None:
        encabezado = self.hoja.row_values(1)
        nuevas = [k for k in registro if k not in encabezado]
        if nuevas:
            encabezado = encabezado + nuevas
            self.hoja.update([encabezado], "A1")
        fila = ["" if registro.get(c) is None else str(registro.get(c, "")) for c in encabezado]
        self.hoja.append_row(fila, value_input_option="USER_ENTERED")


# ----------------------------------------------------------------------------
def obtener_almacen(secrets: Optional[Mapping]) -> Tuple[object, Optional[str]]:
    """Devuelve (almacén, advertencia). Si falla la nube, cae a CSV local."""
    try:
        backend = (secrets or {}).get("storage", {}).get("backend", "local")
    except Exception:  # st.secrets sin archivo lanza excepción
        backend = "local"
    if backend == "local":
        return AlmacenLocal(), None
    try:
        if backend == "drive_csv":
            return AlmacenDriveCSV(secrets), None
        if backend == "sheets":
            return AlmacenSheets(secrets), None
        return AlmacenLocal(), f"Backend desconocido '{backend}'; usando CSV local."
    except Exception as exc:
        return AlmacenLocal(), f"No se pudo conectar con {backend} ({exc}); usando CSV local."
