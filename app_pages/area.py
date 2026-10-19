import streamlit as st

from tablero.config import AREAS_SIN_FUENTE
from tablero.data import datos_visibles, filtrar, periodo_anterior
from tablero.metrics import delta, fmt_num, fmt_pct, kpis, resumen_por

inicio, fin, areas, edificios = st.session_state.filtro
area = st.segmented_control("Área", areas, default=areas[0], required=True, key="area_detalle")
if area not in areas:
    area = areas[0]

if area in AREAS_SIN_FUENTE:
    st.info(f"{area} no usa ServiceDesk. Sus datos vendrán de {AREAS_SIN_FUENTE[area]}.",
            title="Sin fuente de datos", icon=":material/schedule:")
    st.stop()

datos = datos_visibles()
f = filtrar(datos, inicio, fin, [area], edificios)
k = kpis(f)
k0 = kpis(filtrar(datos, *periodo_anterior(inicio, fin), [area], edificios))

st.subheader(f"Tickets y productividad · {area}")
with st.container(horizontal=True):
    st.metric("Creados", fmt_num(k["creados"]), delta(k["creados"], k0["creados"]), delta_color="off", border=True)
    st.metric("Cerrados", fmt_num(k["cerrados"]), delta(k["cerrados"], k0["cerrados"]), border=True)
    st.metric(
        "Cerrados por persona",
        fmt_num(k["cerrados_por_persona"], 1),
        delta(k["cerrados_por_persona"], k0["cerrados_por_persona"]),
        border=True,
    )
    st.metric("SLA", fmt_pct(k["pct_sla"]), delta(k["pct_sla"], k0["pct_sla"], pct=True), border=True)
    st.metric(
        "Resolución (días)",
        fmt_num(k["dias_resolucion"], 1),
        delta(k["dias_resolucion"], k0["dias_resolucion"]),
        delta_color="inverse",
        border=True,
    )
    st.metric("Backlog actual", fmt_num(k["backlog"]), 0, delta_description="abiertos hoy", border=True)

st.subheader("Calidad, proyectos y asistencia")
with st.container(horizontal=True):
    st.metric("Incidentes", fmt_pct(k["pct_incidentes"]), delta(k["pct_incidentes"], k0["pct_incidentes"], pct=True),
              delta_color="inverse", border=True, help="Tickets con categoría Incidente / total")
    st.metric("Cancelados", fmt_pct(k["pct_cancelados"]), delta(k["pct_cancelados"], k0["pct_cancelados"], pct=True),
              delta_color="inverse", border=True)
    st.metric("Proyectos a tiempo", fmt_pct(k["pct_proyectos_a_tiempo"]),
              delta(k["pct_proyectos_a_tiempo"], k0["pct_proyectos_a_tiempo"], pct=True), border=True)
    st.metric("Asistencia", fmt_pct(k["pct_asistencia"]),
              delta(k["pct_asistencia"], k0["pct_asistencia"], pct=True), border=True)
    st.metric("Retardos", fmt_num(k["retardos"]), delta(k["retardos"], k0["retardos"]), delta_color="inverse", border=True)
    st.metric("Faltas", fmt_num(k["faltas"]), delta(k["faltas"], k0["faltas"]), delta_color="inverse", border=True)

t = f["tickets"]
col1, col2 = st.columns([2, 1])
with col1:
    with st.container(border=True):
        st.subheader("Creados vs cerrados por semana")
        flujo = (
            t.assign(cerrado=t["estado"] == "cerrado")
            .groupby("semana")
            .agg(Creados=("ticket_id", "size"), Cerrados=("cerrado", "sum"))
        )
        st.line_chart(flujo, x_label="", y_label="Tickets", alt="Tickets creados y cerrados por semana")
with col2:
    with st.container(border=True):
        st.subheader("Por subárea y categoría")
        mezcla = t.groupby(["subarea", "categoria"]).size().rename("tickets").reset_index()
        st.bar_chart(mezcla, x="subarea", y="tickets", color="categoria", horizontal=True, x_label="Tickets",
                     y_label="", alt="Tickets por subárea y categoría")

with st.container(border=True):
    st.subheader("Equipo")
    equipo = f["colaboradores"].set_index("id")[["nombre", "puesto", "reporta_a"]].join(resumen_por(f, "colaborador_id"))
    equipo = equipo.fillna({"cerrados": 0, "retardos": 0, "faltas": 0})
    st.dataframe(
        equipo.sort_values("cerrados", ascending=False),
        hide_index=True,
        column_order=["nombre", "puesto", "reporta_a", "cerrados", "backlog", "dias_resolucion", "pct_sla", "pct_incidentes",
                      "pct_asistencia", "retardos", "faltas"],
        column_config={
            "nombre": "Colaborador",
            "puesto": "Puesto",
            "reporta_a": "Reporta a",
            "cerrados": st.column_config.NumberColumn("Cerrados"),
            "backlog": st.column_config.NumberColumn("Backlog"),
            "dias_resolucion": st.column_config.NumberColumn("Resolución (días)", format="%.1f"),
            "pct_sla": st.column_config.ProgressColumn("SLA", format="percent", min_value=0, max_value=1),
            "pct_incidentes": st.column_config.NumberColumn("Incidentes", format="percent"),
            "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0, max_value=1),
            "retardos": st.column_config.NumberColumn("Retardos"),
            "faltas": st.column_config.NumberColumn("Faltas"),
        },
        alt=f"Indicadores por colaborador del área {area}",
    )

col3, col4 = st.columns(2)
with col3:
    with st.container(border=True):
        st.subheader("Backlog actual")
        st.dataframe(
            f["backlog"].sort_values("fecha_creacion")[
                ["ticket_id", "subarea", "edificio", "prioridad", "categoria", "estatus", "fecha_creacion", "resolutor"]
            ],
            hide_index=True,
            height=350,
            column_config={
                "ticket_id": st.column_config.NumberColumn("Ticket", format="%d"),
                "subarea": "Subárea",
                "edificio": "Edificio",
                "prioridad": "Prioridad",
                "categoria": "Categoría",
                "estatus": "Estatus",
                "fecha_creacion": st.column_config.DateColumn("Creado", format="DD/MM/YYYY"),
                "resolutor": "Resolutor",
            },
            alt=f"Tickets abiertos del área {area}",
        )
with col4:
    with st.container(border=True):
        st.subheader("Proyectos (demo)")
        proyectos = f["proyectos"].assign(
            avance_real=lambda df: df["avance_real"] / 100, avance_plan=lambda df: df["avance_plan"] / 100
        )
        st.dataframe(
            proyectos[["nombre", "responsable", "estado", "fecha_fin_plan", "avance_plan", "avance_real", "retrasado"]],
            hide_index=True,
            height=350,
            column_config={
                "nombre": "Proyecto",
                "responsable": "Responsable",
                "estado": "Estado",
                "fecha_fin_plan": st.column_config.DateColumn("Fin plan", format="DD/MM/YYYY"),
                "avance_plan": st.column_config.ProgressColumn("Plan", format="percent", min_value=0, max_value=1),
                "avance_real": st.column_config.ProgressColumn("Real", format="percent", min_value=0, max_value=1),
                "retrasado": st.column_config.CheckboxColumn("Retrasado"),
            },
            alt=f"Proyectos del área {area}",
        )
