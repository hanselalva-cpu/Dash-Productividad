import streamlit as st

from tablero.metrics import resumen_por
from tablero.data import datos_visibles, filtrar

inicio, fin, areas, edificios = st.session_state.filtro
datos = datos_visibles()
f = filtrar(datos, inicio, fin, areas, edificios)

personas = (
    f["colaboradores"]
    .set_index("id")[["nombre", "area", "puesto", "reporta_a"]]
    .join(resumen_por(f, "colaborador_id"))
    .fillna({"cerrados": 0, "retardos": 0, "faltas": 0, "dias_vacaciones": 0})
)

with st.container(horizontal=True, vertical_alignment="bottom"):
    buscar = st.text_input("Buscar colaborador", placeholder="Nombre...", icon=":material/search:")
    orden = st.segmented_control(
        "Ordenar por",
        ["Cerrados", "SLA", "Asistencia", "Retardos"],
        default="Cerrados",
        required=True,
        key="personas_orden",
    )

columna_orden = {"Cerrados": "cerrados", "SLA": "pct_sla", "Asistencia": "pct_asistencia", "Retardos": "retardos"}[orden]
vista = personas[personas["nombre"].str.contains(buscar, case=False)] if buscar else personas
vista = vista.sort_values(columna_orden, ascending=False)

with st.container(border=True):
    st.subheader("Línea de reporte")
    todos = datos["colaboradores"]
    if todos["reporta_a_id"].notna().any():
        cerrados = f["tickets"][f["tickets"]["estado"] == "cerrado"].groupby("colaborador_id").size()
        nodos = []
        for _, c in todos.iterrows():
            dentro = c["area"] in areas
            etiqueta = f'{c["nombre"]}\\n{c["puesto"] or ""} · {c["area"]}'
            if dentro and cerrados.get(c["id"], 0):
                etiqueta += f'\\n{cerrados[c["id"]]:,} cerrados'
            estilo = "filled" if dentro else "filled,dashed"
            color = "#DBEAFE" if dentro else "#F1F5F9"
            nodos.append(f'"{c["id"]}" [label="{etiqueta}", style="{estilo}", fillcolor="{color}"];')
        visibles = set(todos["id"])  # el jefe de un usuario restringido no se dibuja
        aristas = [f"\"{c['reporta_a_id']}\" -> \"{c['id']}\";" for _, c in todos.dropna(subset=["reporta_a_id"]).iterrows()
                   if c["reporta_a_id"] in visibles]
        st.graphviz_chart(
            "digraph { rankdir=LR; nodesep=0.15; ranksep=0.6; "
            'node [shape=box, fontname="Arial", fontsize=10, color="#94A3B8"]; edge [color="#94A3B8"]; '
            + " ".join(nodos + aristas) + " }",
            width="stretch",
            alt="Organigrama: a quién reporta cada colaborador",
        )
        st.caption("Tickets cerrados en el periodo. Recuadro punteado: fuera de las áreas filtradas.")
    else:
        st.info("Falta la columna reporta_a en el listado de personal.", icon=":material/account_tree:")

with st.container(border=True):
    st.subheader("Top 15 por tickets cerrados")
    top = personas.nlargest(15, "cerrados")
    st.bar_chart(top, x="nombre", y="cerrados", color="area", horizontal=True, sort="-cerrados",
                 x_label="Cerrados", y_label="", alt="Top 15 colaboradores por tickets cerrados")

with st.container(border=True):
    st.subheader(f"Indicadores por colaborador ({len(vista)})")
    st.dataframe(
        vista,
        hide_index=True,
        column_order=["nombre", "area", "puesto", "reporta_a", "cerrados", "backlog", "dias_resolucion", "pct_sla",
                      "pct_incidentes", "pct_cancelados", "pct_asistencia", "retardos", "faltas", "dias_vacaciones"],
        column_config={
            "nombre": "Colaborador",
            "area": "Área",
            "puesto": "Puesto",
            "reporta_a": "Reporta a",
            "cerrados": st.column_config.NumberColumn("Cerrados"),
            "backlog": st.column_config.NumberColumn("Backlog"),
            "dias_resolucion": st.column_config.NumberColumn("Resolución (días)", format="%.1f"),
            "pct_sla": st.column_config.ProgressColumn("SLA", format="percent", min_value=0, max_value=1),
            "pct_incidentes": st.column_config.NumberColumn("Incidentes", format="percent"),
            "pct_cancelados": st.column_config.NumberColumn("Cancelados", format="percent"),
            "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0, max_value=1),
            "retardos": st.column_config.NumberColumn("Retardos"),
            "faltas": st.column_config.NumberColumn("Faltas"),
            "dias_vacaciones": st.column_config.NumberColumn("Días vacaciones", help="Días hábiles aprobados en el periodo"),
        },
        alt="Indicadores de productividad y asistencia por colaborador",
    )
