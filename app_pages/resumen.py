import streamlit as st

from utils.data import datos_visibles, filtrar, periodo_anterior
from utils.metrics import delta, fmt_num, fmt_pct, kpis, resumen_por

inicio, fin, areas, edificios = st.session_state.filtro
datos = datos_visibles()
f = filtrar(datos, inicio, fin, areas, edificios)
k = kpis(f)
k0 = kpis(filtrar(datos, *periodo_anterior(inicio, fin), areas, edificios))

with st.container(horizontal=True):
    st.metric("Tickets cerrados", fmt_num(k["cerrados"]), delta(k["cerrados"], k0["cerrados"]), border=True)
    st.metric("Cumplimiento SLA", fmt_pct(k["pct_sla"]), delta(k["pct_sla"], k0["pct_sla"], pct=True), border=True)
    st.metric(
        "Resolución (días)",
        fmt_num(k["dias_resolucion"], 1),
        delta(k["dias_resolucion"], k0["dias_resolucion"]),
        delta_color="inverse",
        border=True,
    )
    st.metric("Backlog actual", fmt_num(k["backlog"]), 0, delta_description="abiertos hoy", border=True)
    st.metric(
        "Cancelados",
        fmt_pct(k["pct_cancelados"]),
        delta(k["pct_cancelados"], k0["pct_cancelados"], pct=True),
        delta_color="inverse",
        border=True,
    )
    st.metric(
        "Proyectos a tiempo",
        fmt_pct(k["pct_proyectos_a_tiempo"]),
        delta(k["pct_proyectos_a_tiempo"], k0["pct_proyectos_a_tiempo"], pct=True),
        border=True,
    )
    st.metric(
        "Asistencia", fmt_pct(k["pct_asistencia"]), delta(k["pct_asistencia"], k0["pct_asistencia"], pct=True), border=True
    )
    st.metric("Retardos", fmt_num(k["retardos"]), delta(k["retardos"], k0["retardos"]), delta_color="inverse", border=True)

with st.container(border=True):
    st.subheader("Scorecard por área")
    tabla = resumen_por(f, "area").reindex(areas)
    st.dataframe(
        tabla[
            [
                "personas", "creados", "cerrados", "cerrados_por_persona", "backlog", "dias_resolucion", "pct_sla",
                "pct_incidentes", "pct_cancelados", "proyectos", "pct_proyectos_a_tiempo", "pct_asistencia", "faltas",
                "retardos", "dias_vacaciones",
            ]
        ],
        column_config={
            "_index": st.column_config.TextColumn("Área"),
            "personas": st.column_config.NumberColumn("Personas", help="Resolutores con tickets"),
            "creados": st.column_config.NumberColumn("Creados"),
            "cerrados": st.column_config.NumberColumn("Cerrados"),
            "cerrados_por_persona": st.column_config.NumberColumn("Cerrados/persona", format="%.1f"),
            "backlog": st.column_config.NumberColumn("Backlog", help="Tickets abiertos hoy"),
            "dias_resolucion": st.column_config.NumberColumn("Resolución (días)", format="%.1f"),
            "pct_sla": st.column_config.ProgressColumn("SLA", format="percent", min_value=0, max_value=1),
            "pct_incidentes": st.column_config.NumberColumn("Incidentes", format="percent"),
            "pct_cancelados": st.column_config.NumberColumn("Cancelados", format="percent"),
            "proyectos": st.column_config.NumberColumn("Proyectos"),
            "pct_proyectos_a_tiempo": st.column_config.ProgressColumn(
                "Proy. a tiempo", format="percent", min_value=0, max_value=1
            ),
            "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0, max_value=1),
            "faltas": st.column_config.NumberColumn("Faltas"),
            "retardos": st.column_config.NumberColumn("Retardos"),
            "dias_vacaciones": st.column_config.NumberColumn("Días vacaciones"),
        },
        alt="Scorecard de indicadores por área",
    )

semanal = f["tickets"][f["tickets"]["estado"] == "cerrado"].groupby(["semana", "area"]).size().rename("cerrados")
col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        st.subheader("Tickets cerrados por semana")
        st.line_chart(semanal.reset_index(), x="semana", y="cerrados", color="area", x_label="", y_label="Cerrados",
                      alt="Tickets cerrados por semana y área")
with col2:
    with st.container(border=True):
        st.subheader("Cumplimiento SLA por área")
        st.bar_chart((tabla["pct_sla"] * 100).round(1).rename("SLA %").dropna(), horizontal=True, x_label="% SLA",
                     y_label="", alt="Porcentaje de cumplimiento de SLA por área")

col3, col4 = st.columns(2)
with col3:
    with st.container(border=True):
        st.subheader("Retardos y faltas por área")
        st.bar_chart(tabla[["retardos", "faltas"]], stack=False, x_label="", y_label="Eventos",
                     alt="Retardos y faltas por área")
with col4:
    with st.container(border=True):
        st.subheader("Backlog actual por prioridad")
        backlog = f["backlog"].groupby(["area", "prioridad"]).size().rename("tickets").reset_index()
        st.bar_chart(backlog, x="area", y="tickets", color="prioridad", x_label="", y_label="Tickets",
                     alt="Backlog actual por área y prioridad")
