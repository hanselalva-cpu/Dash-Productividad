import streamlit as st

from tablero.data import datos_visibles
from tablero.metrics import fmt_num, fmt_pct
from tablero.persona import años_disponibles, mensual, totales

datos = datos_visibles()
col = datos["colaboradores"].sort_values("nombre")
if col.empty:
    st.info("No hay personas visibles para tu usuario.", icon=":material/person_off:")
    st.stop()

etiquetas = {r.id: f"{r.nombre} · {r.area}" for r in col.itertuples()}
with st.container(horizontal=True, vertical_alignment="bottom"):
    persona = st.selectbox("Persona", list(etiquetas), format_func=etiquetas.get, key="ficha_persona")
    año = st.selectbox("Año", años_disponibles(datos), key="ficha_año", width=120)
st.caption("Año completo de la persona; no aplica el periodo ni las áreas de la barra lateral. "
           "Los tickets cerrados cuentan en el mes en que se resolvieron.")

m = mensual(datos, [persona], año)
tot = totales(m).iloc[0]
info = col.set_index("id").loc[persona]

with st.container(horizontal=True):
    st.metric("Tickets cerrados", fmt_num(tot["cerrados"]), border=True)
    st.metric("Cumplimiento SLA", fmt_pct(tot["pct_sla"]), border=True)
    st.metric("Resolución (días)", fmt_num(tot["dias_resolucion"], 1), border=True)
    st.metric("Asistencia", fmt_pct(tot["pct_asistencia"]), border=True)
    st.metric("Retardos", fmt_num(tot["retardos"]), border=True)
    st.metric("Faltas", fmt_num(tot["faltas"]), border=True)
    st.metric("Días de vacaciones", fmt_num(tot["vacaciones"]), border=True)

st.caption(
    f"{info['puesto'] or ''} · {info['area']}"
    + (f" · Reporta a {info['reporta_a']}" if info.get("reporta_a") else "")
    + f" · Vacaciones en {año}: {tot['meses_con_vacaciones']}"
)

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.subheader("Tickets cerrados por mes")
        st.bar_chart(m, x="mes_fecha", y="cerrados", x_label="", y_label="Cerrados",
                     alt=f"Tickets cerrados por mes en {año}")
with c2:
    with st.container(border=True):
        st.subheader("Asistencia y retardos por mes")
        st.bar_chart(
            m.rename(columns={"retardos": "Retardos", "faltas": "Faltas", "vacaciones": "Vacaciones"}),
            x="mes_fecha", y=["Retardos", "Faltas", "Vacaciones"], stack=False, x_label="", y_label="Días",
            alt=f"Retardos, faltas y días de vacaciones por mes en {año}",
        )

with st.container(border=True):
    st.subheader(f"Mes por mes · {año}")
    st.dataframe(
        m,
        hide_index=True,
        column_order=["mes_nombre", "cerrados", "pct_sla", "dias_resolucion", "pct_asistencia", "laborables",
                      "retardos", "faltas", "vacaciones", "incapacidad", "sin_salida"],
        column_config={
            "mes_nombre": "Mes",
            "cerrados": st.column_config.NumberColumn("Cerrados"),
            "pct_sla": st.column_config.ProgressColumn("SLA", format="percent", min_value=0, max_value=1),
            "dias_resolucion": st.column_config.NumberColumn("Resolución (días)", format="%.1f"),
            "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0, max_value=1),
            "laborables": st.column_config.NumberColumn("Días laborables"),
            "retardos": st.column_config.NumberColumn("Retardos"),
            "faltas": st.column_config.NumberColumn("Faltas"),
            "vacaciones": st.column_config.NumberColumn("Vacaciones"),
            "incapacidad": st.column_config.NumberColumn("Incapacidad"),
            "sin_salida": st.column_config.NumberColumn("Sin checada salida"),
        },
        alt=f"Indicadores mensuales de {info['nombre']} en {año}",
    )
