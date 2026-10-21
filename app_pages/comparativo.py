import pandas as pd
import streamlit as st

from tablero.config import AREAS_SIN_FUENTE
from tablero.data import datos_visibles, filtrar, periodo_anterior
from tablero.metrics import resumen_por
from tablero.persona import INDICADORES_PERSONA, años_disponibles, mensual, totales

inicio, fin, areas, edificios = st.session_state.filtro
datos = datos_visibles()

modo = st.segmented_control("Comparar", ["Áreas", "Personas"], default="Áreas", required=True, key="comparativo_modo")

if modo == "Personas":
    col_p = datos["colaboradores"].sort_values("nombre")
    etiquetas = {r.id: f"{r.nombre} · {r.area}" for r in col_p.itertuples()}
    with st.container(horizontal=True, vertical_alignment="bottom"):
        elegidos = st.multiselect("Personas", list(etiquetas), format_func=etiquetas.get, max_selections=6,
                                  placeholder="Elige 2 o más personas", key="comparativo_personas")
        año = st.selectbox("Año", años_disponibles(datos), key="comparativo_año", width=120)
    st.caption("Año completo de cada persona; no aplica el periodo ni las áreas de la barra lateral.")
    if len(elegidos) < 2:
        st.info("Elige al menos 2 personas para compararlas.", icon=":material/group_add:")
        st.stop()

    m = mensual(datos, elegidos, año)
    tot = totales(m).set_index("colaborador")

    with st.container(border=True):
        st.subheader(f"Año completo · {año}")
        st.dataframe(
            tot,
            column_order=["cerrados", "pct_sla", "dias_resolucion", "pct_asistencia", "retardos", "faltas",
                          "vacaciones", "meses_con_vacaciones"],
            column_config={
                "_index": st.column_config.TextColumn("Persona"),
                "cerrados": st.column_config.NumberColumn("Cerrados"),
                "pct_sla": st.column_config.ProgressColumn("SLA", format="percent", min_value=0, max_value=1),
                "dias_resolucion": st.column_config.NumberColumn("Resolución (días)", format="%.1f"),
                "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0,
                                                                  max_value=1),
                "retardos": st.column_config.NumberColumn("Retardos"),
                "faltas": st.column_config.NumberColumn("Faltas"),
                "vacaciones": st.column_config.NumberColumn("Días vacaciones"),
                "meses_con_vacaciones": st.column_config.TextColumn("Meses con vacaciones (días)", width="large"),
            },
            alt=f"Comparativo anual {año} de las personas elegidas",
        )
        mejores = []
        for nombre, (c, _, mayor_mejor) in INDICADORES_PERSONA.items():
            serie = tot[c].dropna()
            if mayor_mejor is None or serie.empty or serie.nunique() == 1:
                continue
            mejores.append(f"**{nombre}:** {serie.idxmax() if mayor_mejor else serie.idxmin()}")
        if mejores:
            st.markdown("Mejor en cada indicador — " + " · ".join(mejores))

    indicador_p = st.pills("Indicador", list(INDICADORES_PERSONA), default="Tickets cerrados", selection_mode="single",
                           key="comparativo_indicador_persona") or "Tickets cerrados"
    c, fmt_p, _ = INDICADORES_PERSONA[indicador_p]
    escala_p = 100 if fmt_p == "percent" else 1
    sufijo = " (%)" if fmt_p == "percent" else ""

    c1, c2 = st.columns([3, 2])
    with c1:
        with st.container(border=True, height="stretch"):
            st.subheader(f"{indicador_p} por mes")
            st.line_chart(m.assign(valor=m[c] * escala_p), x="mes_fecha", y="valor", color="colaborador",
                          x_label="", y_label=f"{indicador_p}{sufijo}",
                          alt=f"{indicador_p} por mes de las personas elegidas")
    with c2:
        with st.container(border=True, height="stretch"):
            st.subheader("Mes por mes")
            tabla_mes = m.pivot_table(index=["mes", "mes_nombre"], columns="colaborador", values=c, aggfunc="first")
            tabla_mes = tabla_mes.reset_index(level="mes", drop=True)
            st.dataframe(
                tabla_mes,
                column_config={"_index": st.column_config.TextColumn("Mes"),
                               **{p: st.column_config.NumberColumn(p, format=fmt_p) for p in tabla_mes.columns}},
                alt=f"{indicador_p} mes por mes de las personas elegidas",
            )
    st.stop()
f = filtrar(datos, inicio, fin, areas, edificios)
f0 = filtrar(datos, *periodo_anterior(inicio, fin), areas, edificios)

# indicador -> (columna, formato, mayor es mejor)
INDICADORES = {
    "Cerrados": ("cerrados", "%d", True),
    "Cerrados por persona": ("cerrados_por_persona", "%.1f", True),
    "Cumplimiento SLA": ("pct_sla", "percent", True),
    "Resolución (días)": ("dias_resolucion", "%.1f", False),
    "Backlog actual": ("backlog", "%d", False),
    "% Incidentes": ("pct_incidentes", "percent", False),
    "% Cancelados": ("pct_cancelados", "percent", False),
    "Asistencia": ("pct_asistencia", "percent", True),
    "Retardos por persona": ("retardos_por_persona", "%.1f", False),
    "Faltas": ("faltas", "%d", False),
}


def tabla_areas(filtrado: dict) -> pd.DataFrame:
    t = resumen_por(filtrado, "area").reindex(areas)
    t["retardos_por_persona"] = t["retardos"] / t["personas"].where(t["personas"] > 0)
    return t


actual, anterior = tabla_areas(f), tabla_areas(f0)
# Áreas sin datos de tickets ni asistencia no compiten en el ranking
con_datos = actual[(actual["creados"] > 0) | (actual["pct_asistencia"].notna())].index.tolist()
sin_datos = [a for a in areas if a not in con_datos]

indicador = st.pills("Indicador", list(INDICADORES), default="Cumplimiento SLA", selection_mode="single",
                     key="comparativo_indicador") or "Cumplimiento SLA"
col, fmt, mayor_mejor = INDICADORES[indicador]
escala = 100 if fmt == "percent" else 1

c1, c2 = st.columns([3, 2])
with c1:
    with st.container(border=True, height="stretch"):
        st.subheader(indicador)
        datos_barra = (actual.loc[con_datos, col] * escala).rename(indicador).dropna()
        datos_barra = datos_barra.sort_values(ascending=not mayor_mejor)
        st.bar_chart(
            datos_barra.reset_index().rename(columns={"index": "area"}),
            x="area", y=indicador, horizontal=True, sort=f"{'-' if mayor_mejor else ''}{indicador}",
            x_label=f"{indicador}{' (%)' if fmt == 'percent' else ''}", y_label="",
            alt=f"{indicador} por área",
        )
        st.caption("Mejor arriba." + (" Menor es mejor." if not mayor_mejor else ""))
with c2:
    with st.container(border=True, height="stretch"):
        st.subheader("Contra el periodo anterior")
        cambio = pd.DataFrame({"actual": actual.loc[con_datos, col], "anterior": anterior.loc[con_datos, col]})
        cambio["cambio"] = cambio["actual"] - cambio["anterior"]
        cambio["tendencia"] = cambio["cambio"].apply(
            lambda x: "—" if pd.isna(x) or x == 0 else ("Mejora" if (x > 0) == mayor_mejor else "Empeora")
        )
        st.dataframe(
            cambio.sort_values("actual", ascending=not mayor_mejor),
            column_config={
                "_index": st.column_config.TextColumn("Área"),
                "actual": st.column_config.NumberColumn("Actual", format=fmt),
                "anterior": st.column_config.NumberColumn("Anterior", format=fmt),
                "cambio": st.column_config.NumberColumn("Cambio", format=fmt if fmt != "%d" else "%+d"),
                "tendencia": "Tendencia",
            },
            alt=f"{indicador}: periodo actual contra anterior por área",
        )


# Tendencia semanal del indicador elegido
def semanal(filtrado: dict, columna: str) -> pd.DataFrame | None:
    t, a = filtrado["tickets"], filtrado["asistencias"]
    personas = filtrado["colaboradores"].groupby("area").size()
    cerr = t[t["estado"] == "cerrado"]
    g = None
    if columna == "cerrados":
        g = cerr.groupby(["semana", "area"]).size()
    elif columna == "cerrados_por_persona":
        g = cerr.groupby(["semana", "area"]).size() / cerr.groupby(["semana", "area"]).size().index.get_level_values(
            "area").map(personas).to_numpy()
    elif columna == "pct_sla":
        g = cerr.groupby(["semana", "area"])["cumple_sla"].mean() * 100
    elif columna == "dias_resolucion":
        g = cerr.groupby(["semana", "area"])["dias_resolucion"].mean()
    elif columna == "pct_incidentes":
        g = t.groupby(["semana", "area"])["categoria"].apply(lambda s: (s == "Incidente").mean() * 100)
    elif columna == "pct_cancelados":
        g = t.groupby(["semana", "area"])["estado"].apply(lambda s: (s == "cancelado").mean() * 100)
    elif columna == "pct_asistencia":
        s = a.groupby(["semana", "area"])[["presente", "laborable"]].sum()
        g = s["presente"] / s["laborable"].where(s["laborable"] > 0) * 100
    elif columna == "retardos_por_persona":
        r = a.groupby(["semana", "area"])["retardo"].sum()
        g = r / r.index.get_level_values("area").map(personas).to_numpy()
    elif columna == "faltas":
        g = a[a["estatus"] == "falta"].groupby(["semana", "area"]).size()
    if g is None or g.empty:
        return None
    return g.rename("valor").reset_index()


with st.container(border=True):
    st.subheader(f"{indicador} por semana")
    serie = semanal(f, col)
    if serie is None:
        st.info("Este indicador es una foto de hoy; no tiene tendencia semanal.", icon=":material/info:")
    else:
        st.line_chart(serie, x="semana", y="valor", color="area", x_label="",
                      y_label=f"{indicador}{' (%)' if fmt == 'percent' else ''}",
                      alt=f"Tendencia semanal de {indicador} por área")

with st.container(border=True):
    st.subheader("Ranking general")
    st.caption("Posición de cada área en cada indicador (1 = mejor). El ranking general es el promedio de posiciones.")
    posiciones = pd.DataFrame(
        {
            nombre: actual.loc[con_datos, c].rank(ascending=not mejor, method="min")
            for nombre, (c, _, mejor) in INDICADORES.items()
        }
    )
    posiciones.insert(0, "Promedio", posiciones.mean(axis=1).round(1))
    posiciones.insert(0, "Ranking", posiciones["Promedio"].rank(method="min").astype("Int64"))
    st.dataframe(
        posiciones.sort_values("Ranking"),
        column_config={
            "_index": st.column_config.TextColumn("Área"),
            "Ranking": st.column_config.NumberColumn("Ranking", format="%d"),
            **{n: st.column_config.NumberColumn(n, format="%d") for n in INDICADORES},
        },
        alt="Posición de cada área por indicador",
    )
    if sin_datos:
        motivo = ", ".join(f"{a} ({AREAS_SIN_FUENTE.get(a, 'sin datos en el periodo')})" for a in sin_datos)
        st.caption(f"Fuera del ranking: {motivo}.")
