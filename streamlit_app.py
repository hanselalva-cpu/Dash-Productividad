from datetime import date, timedelta

import streamlit as st

from utils.config import AREAS, AREAS_SIN_FUENTE
from utils.data import EDIFICIOS_LISTA, cargar_datos, supabase_configurado

st.set_page_config(page_title="Productividad por área", page_icon=":material/monitoring:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/resumen.py", title="Resumen general", icon=":material/dashboard:"),
        st.Page("app_pages/area.py", title="Detalle por área", icon=":material/lan:"),
        st.Page("app_pages/personas.py", title="Personas", icon=":material/group:"),
        st.Page("app_pages/asistencia.py", title="Asistencia y vacaciones", icon=":material/event_available:"),
    ],
    position="top",
)

hoy = date.today()
with st.sidebar:
    st.header("Filtros")
    periodo = st.date_input(
        "Periodo",
        value=(hoy - timedelta(days=29), hoy),
        max_value=hoy,
        format="DD/MM/YYYY",
        key="periodo",
    )
    areas = st.pills("Áreas", AREAS, selection_mode="multi", default=AREAS, key="areas")
    edificios = st.multiselect(
        "Edificios", EDIFICIOS_LISTA, default=EDIFICIOS_LISTA, key="edificios", help="Aplica solo a tickets"
    )

    st.divider()
    datos = cargar_datos()
    st.markdown("**Fuentes de datos**")
    for nombre, fuente in datos["fuentes"].items():
        icono = ":material/science:" if fuente == "Demo" else ":material/cloud_done:"
        st.caption(f"{icono} {nombre.capitalize()}: {fuente}")
    for area, fuente in AREAS_SIN_FUENTE.items():
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

if len(periodo) < 2:
    st.info("Selecciona fecha inicial y final del periodo.", icon=":material/date_range:")
    st.stop()
if not areas or not edificios:
    st.info("Selecciona al menos un área y un edificio.", icon=":material/filter_alt:")
    st.stop()

st.session_state.filtro = (periodo[0], periodo[1], areas, edificios)

st.title(page.title)
st.caption(f"{periodo[0]:%d/%m/%Y} – {periodo[1]:%d/%m/%Y} · comparado contra el periodo anterior de igual duración")
page.run()
