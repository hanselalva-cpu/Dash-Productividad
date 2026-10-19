"""Quién ve qué: según el correo del usuario y el organigrama (data/personal.csv / tabla personal).

- Persona sin jefe en el organigrama (Dirección): ve todo.
- Cualquier otra persona: ve su equipo completo hacia abajo (ella + quienes le reportan, recursivo).
- Correo no registrado en Secrets [accesos]: sin acceso.
- Corriendo en localhost sin login: ve todo (uso local del autor).
"""

from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from utils.config import AREAS


def correo_actual() -> str | None:
    try:
        correo = st.user.get("email")
    except Exception:
        correo = None
    return str(correo).strip().lower() if correo else None


def es_local() -> bool:
    try:
        return urlparse(st.context.url or "").hostname in ("localhost", "127.0.0.1")
    except Exception:
        return False


def _accesos() -> dict[str, str]:
    try:
        return {str(k).strip().lower(): str(v).strip() for k, v in st.secrets.get("accesos", {}).items()}
    except Exception:
        return {}


def equipo(col: pd.DataFrame, raiz: str) -> set[str]:
    """IDs de la persona y de todos los que le reportan directa o indirectamente."""
    hijos = col.dropna(subset=["reporta_a_id"]).groupby("reporta_a_id")["id"].apply(list).to_dict()
    visto, pendientes = set(), [raiz]
    while pendientes:
        actual = pendientes.pop()
        if actual not in visto:
            visto.add(actual)
            pendientes.extend(hijos.get(actual, []))
    return visto


def resolver_acceso(col: pd.DataFrame) -> dict | None:
    """{"nombre", "correo", "personas" (None = todas), "areas"} o None si no tiene acceso."""
    correo = correo_actual()
    if correo is None and es_local():
        return {"nombre": "Local", "correo": None, "personas": None, "areas": AREAS}
    id_empleado = _accesos().get(correo or "")
    persona = col[col["id"] == id_empleado]
    if not id_empleado or persona.empty:
        return None
    p = persona.iloc[0]
    if pd.isna(p["reporta_a_id"]):
        return {"nombre": p["nombre"], "correo": correo, "personas": None, "areas": AREAS}
    ids = equipo(col, id_empleado)
    areas_equipo = set(col.loc[col["id"].isin(ids), "area"])
    return {"nombre": p["nombre"], "correo": correo, "personas": ids,
            "areas": [a for a in AREAS if a in areas_equipo]}


def restringir(d: dict, personas: set[str] | None, areas: list[str]) -> dict:
    """Recorta todos los datos a lo que el usuario puede ver."""
    if personas is None:
        return d
    t = d["tickets"]
    return {
        **d,
        "colaboradores": d["colaboradores"][d["colaboradores"]["id"].isin(personas)],
        # Tickets de sus áreas resueltos por su equipo, más los aún sin asignar
        "tickets": t[t["area"].isin(areas) & (t["colaborador_id"].isin(personas) | t["colaborador_id"].isna())],
        "proyectos": d["proyectos"][d["proyectos"]["area"].isin(areas)],
        "asistencias": d["asistencias"][d["asistencias"]["colaborador_id"].isin(personas)],
        "vacaciones": d["vacaciones"][d["vacaciones"]["colaborador_id"].isin(personas)],
    }
