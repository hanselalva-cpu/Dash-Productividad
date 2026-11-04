from datetime import date, timedelta

import streamlit as st

from tablero.acceso import cerrar_sesion, correo_actual, es_local, formulario_login, resolver_acceso
from tablero.config import AREAS_SIN_FUENTE
from tablero.data import EDIFICIOS_LISTA, cargar_datos, supabase_configurado

st.set_page_config(page_title="Productividad por área", page_icon=":material/monitoring:", layout="wide")

if correo_actual() is None and not es_local():
    formulario_login()
    st.stop()

page = st.navigation(
    [
        st.Page("app_pages/resumen.py", title="Resumen general", icon=":material/dashboard:"),
        st.Page("app_pages/comparativo.py", title="Comparativo", icon=":material/compare_arrows:"),
        st.Page("app_pages/area.py", title="Detalle por área", icon=":material/lan:"),
        st.Page("app_pages/proyectos.py", title="Proyectos", icon=":material/view_timeline:"),
        st.Page("app_pages/personas.py", title="Personas", icon=":material/group:"),
        st.Page("app_pages/ficha.py", title="Ficha de persona", icon=":material/badge:"),
        st.Page("app_pages/asistencia.py", title="Asistencia y vacaciones", icon=":material/event_available:"),
    ],
    position="top",
)

datos = cargar_datos()
# Tras un despliegue, Streamlit Cloud puede seguir con módulos o caché de la versión anterior:
# si faltan datos que esperan las páginas, recarga los módulos y la caché una vez.
CLAVES_DATOS = {"tickets", "colaboradores", "proyectos_todos", "asignaciones", "proyectos_area", "asistencias",
                "vacaciones", "fuentes"}
if not CLAVES_DATOS <= datos.keys() and not st.session_state.get("datos_recargados"):
    import importlib

    import tablero.acceso
    import tablero.config
    import tablero.data
    import tablero.metrics
    import tablero.persona
    import tablero.proyectos

    for modulo in (tablero.config, tablero.proyectos, tablero.data, tablero.acceso, tablero.metrics, tablero.persona):
        importlib.reload(modulo)
    st.cache_data.clear()
    st.session_state.datos_recargados = True
    st.rerun()
acceso = resolver_acceso(datos["colaboradores"])
st.session_state.acceso = acceso
if acceso is None:
    st.error(
        f"El correo {correo_actual() or '(sin correo)'} no tiene acceso a este dashboard. "
        "Pide al administrador que lo dé de alta.",
        title="Sin acceso",
        icon=":material/lock:",
    )
    if st.session_state.get("correo_login"):
        st.button("Cerrar sesión", icon=":material/logout:", on_click=cerrar_sesion)
    st.stop()

hoy = date.today()
with st.sidebar:
    if acceso["correo"]:
        st.caption(f":material/account_circle: {acceso['nombre']} · {acceso['correo']}")
        if acceso["personas"] is not None:
            st.caption(f"Vista de tu equipo: {len(acceso['personas'])} personas")
        if st.session_state.get("correo_login"):
            st.button("Cerrar sesión", icon=":material/logout:", on_click=cerrar_sesion, width="stretch")

    st.header("Filtros")
    with st.container(horizontal=True):
        fecha_inicio = st.date_input("Fecha inicio", value=hoy - timedelta(days=29), max_value=hoy,
                                     format="DD/MM/YYYY", key="fecha_inicio")
        fecha_fin = st.date_input("Fecha fin", value=hoy, max_value=hoy, format="DD/MM/YYYY", key="fecha_fin")
    areas = st.pills("Áreas", acceso["areas"], selection_mode="multi", default=acceso["areas"],
                     key=f"areas_{acceso['correo'] or 'local'}")
    edificios = st.multiselect(
        "Edificios", EDIFICIOS_LISTA, default=EDIFICIOS_LISTA, key="edificios", help="Aplica solo a tickets"
    )

    st.divider()
    st.markdown("**Fuentes de datos**")
    for nombre, fuente in datos["fuentes"].items():
        icono = ":material/science:" if fuente == "Demo" else ":material/cloud_done:"
        st.caption(f"{icono} {nombre.capitalize()}: {fuente}")
    for area, fuente in AREAS_SIN_FUENTE.items():
        if area in acceso["areas"]:
            st.caption(f":material/schedule: {area}: {fuente}")
    if etl := datos["etl"]:
        estado = ":green[ok]" if etl["estado"] == "ok" else ":red[error]"
        st.caption(f"Última carga de datos: {etl['fin'][:16].replace('T', ' ')} · {estado}")
    if not supabase_configurado():
        st.warning(
            "Configura `.streamlit/secrets.toml` para leer Supabase.",
            title="Tickets en modo demo",
            icon=":material/science:",
        )
    if st.button("Actualizar datos", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
        st.rerun()

if fecha_inicio > fecha_fin:
    st.warning("La fecha de inicio debe ser anterior o igual a la fecha fin.", icon=":material/date_range:")
    st.stop()
if not areas or not edificios:
    st.info("Selecciona al menos un área y un edificio.", icon=":material/filter_alt:")
    st.stop()

st.session_state.filtro = (fecha_inicio, fecha_fin, areas, edificios)

st.title(page.title)
st.caption(f"{fecha_inicio:%d/%m/%Y} – {fecha_fin:%d/%m/%Y} · comparado contra el periodo anterior de igual duración")
page.run()
