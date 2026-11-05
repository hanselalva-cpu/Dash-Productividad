"""Quién ve qué: según el correo del usuario y el organigrama (data/personal.csv / tabla personal).

- Persona sin jefe en el organigrama (Dirección): ve todo.
- Cualquier otra persona: ve su equipo completo hacia abajo (ella + quienes le reportan, recursivo).
- Correo no registrado en Secrets [accesos]: sin acceso.
- Corriendo en localhost sin login: ve todo (uso local del autor).

Identidad: el correo de st.user si la plataforma lo da; si no (Streamlit Community Cloud no lo pasa),
login propio con correo + contraseña. Las contraseñas viven en Secrets [usuarios] como hash PBKDF2
(generar con `python -m tools.crear_usuario`).
"""

import hashlib
import hmac
import time
from urllib.parse import urlparse

import pandas as pd
import streamlit as st

from tablero.config import AREAS

ITERACIONES = 200_000
MAX_INTENTOS = 5
ESPERA_SEG = 60


def hash_contrasena(contrasena: str, sal: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), sal, ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal.hex()}${digest.hex()}"


def verificar_contrasena(contrasena: str, guardado: str) -> bool:
    try:
        _, iteraciones, sal, esperado = guardado.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode("utf-8"), bytes.fromhex(sal), int(iteraciones))
        return hmac.compare_digest(digest.hex(), esperado)
    except (ValueError, AttributeError):
        return False


def _usuarios() -> dict[str, str]:
    try:
        return {str(k).strip().lower(): str(v) for k, v in st.secrets.get("usuarios", {}).items()}
    except Exception:
        return {}


def _correo_plataforma() -> str | None:
    try:
        return st.user.get("email")
    except Exception:
        return None


def correo_actual() -> str | None:
    correo = _correo_plataforma() or st.session_state.get("correo_login")
    return str(correo).strip().lower() if correo else None


def formulario_login() -> None:
    """Pide correo y contraseña; al validar guarda el correo en la sesión y recarga."""
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("Productividad por área")
        bloqueo = st.session_state.get("login_bloqueado_hasta", 0)
        if time.time() < bloqueo:
            st.error(f"Demasiados intentos. Espera {int(bloqueo - time.time())} segundos.", icon=":material/timer:")
            return
        with st.form("login", border=True):
            correo = st.text_input("Correo", placeholder="nombre@econtactsol.com", autocomplete="username")
            contrasena = st.text_input("Contraseña", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", icon=":material/login:", type="primary", width="stretch")
        if entrar:
            correo = correo.strip().lower()
            guardado = _usuarios().get(correo)
            if guardado and verificar_contrasena(contrasena, guardado):
                st.session_state.correo_login = correo
                st.session_state.login_intentos = 0
                st.rerun()
            intentos = st.session_state.get("login_intentos", 0) + 1
            st.session_state.login_intentos = intentos
            if intentos >= MAX_INTENTOS:
                st.session_state.login_bloqueado_hasta = time.time() + ESPERA_SEG
                st.session_state.login_intentos = 0
            st.error("Correo o contraseña incorrectos.", icon=":material/lock:")


def cerrar_sesion() -> None:
    st.session_state.pop("correo_login", None)
    st.session_state.pop("acceso", None)


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


def calendario_vacaciones(col: pd.DataFrame, id_empleado: str, ids_equipo: set[str]) -> set[str]:
    """Para coordinar coberturas: su equipo, su jefe directo y quienes reportan al mismo jefe."""
    jefe = col.loc[col["id"] == id_empleado, "reporta_a_id"].dropna()
    if jefe.empty:
        return set(ids_equipo)
    jefe = jefe.iloc[0]
    pares = set(col.loc[col["reporta_a_id"] == jefe, "id"])
    return set(ids_equipo) | {jefe} | pares


def resolver_acceso(col: pd.DataFrame) -> dict | None:
    """{"nombre", "correo", "personas" (None = todas), "areas", "vacaciones_de"} o None si no tiene acceso.

    vacaciones_de: a quién puede ver en el calendario de vacaciones (None = todos).
    """
    correo = correo_actual()
    if correo is None and es_local():
        return {"nombre": "Local", "correo": None, "personas": None, "areas": AREAS, "vacaciones_de": None}
    id_empleado = _accesos().get(correo or "")
    persona = col[col["id"] == id_empleado]
    if not id_empleado or persona.empty:
        return None
    p = persona.iloc[0]
    if pd.isna(p["reporta_a_id"]):
        return {"nombre": p["nombre"], "correo": correo, "personas": None, "areas": AREAS, "vacaciones_de": None}
    ids = equipo(col, id_empleado)
    areas_equipo = set(col.loc[col["id"].isin(ids), "area"])
    return {"nombre": p["nombre"], "correo": correo, "personas": ids,
            "areas": [a for a in AREAS if a in areas_equipo],
            "vacaciones_de": calendario_vacaciones(col, id_empleado, ids)}


def restringir(d: dict, personas: set[str] | None, areas: list[str], vacaciones_de: set[str] | None = None) -> dict:
    """Recorta todos los datos a lo que el usuario puede ver."""
    if personas is None:
        return d
    vac = d["vacaciones_calendario"]
    t = d["tickets"]
    return {
        **d,
        "colaboradores": d["colaboradores"][d["colaboradores"]["id"].isin(personas)],
        # Tickets de sus áreas resueltos por su equipo, más los aún sin asignar
        "tickets": t[t["area"].isin(areas) & (t["colaborador_id"].isin(personas) | t["colaborador_id"].isna())],
        **_proyectos_visibles(d, personas, areas),
        "asistencias": d["asistencias"][d["asistencias"]["colaborador_id"].isin(personas)],
        "vacaciones": d["vacaciones"][d["vacaciones"]["colaborador_id"].isin(personas)],
        "vacaciones_calendario": vac[vac["colaborador_id"].isin(vacaciones_de or personas)],
    }


def _proyectos_visibles(d: dict, personas: set[str], areas: list[str]) -> dict:
    """Proyectos donde participa alguien de su equipo (con todos sus responsables)."""
    a = d["asignaciones"]
    p = d["proyectos_todos"]
    visibles = set(a.loc[a["id_empleado"].isin(personas), "proyecto_id"])
    visibles |= set(p.loc[p["portafolio_id"].isin(personas), "proyecto_id"])  # la PM ve todo su portafolio
    pa = d["proyectos_area"]
    return {
        "proyectos_todos": d["proyectos_todos"][d["proyectos_todos"]["proyecto_id"].isin(visibles)],
        "asignaciones": a[a["proyecto_id"].isin(visibles)],
        "proyectos_area": pa[pa["proyecto_id"].isin(visibles) & pa["area"].isin(areas)],
    }
