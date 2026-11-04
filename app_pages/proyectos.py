from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from tablero.data import datos_visibles
from tablero.metrics import fmt_num, fmt_pct
from tablero.proyectos import ESTADOS_ACTIVOS, ESTADOS_PROYECTO, ROLES_PROYECTO, UMBRAL_ALTO, UMBRAL_MEDIO

COLOR_ESTADO = {"En desarrollo": "#1D4ED8", "En pruebas": "#0EA5E9", "En espera": "#D97706", "Terminado": "#059669",
                "Cancelado": "#94A3B8"}
ESCALA_ESTADO = alt.Scale(domain=ESTADOS_PROYECTO, range=[COLOR_ESTADO[e] for e in ESTADOS_PROYECTO])
COLOR_SEMAFORO = {"Atención alta": "red", "Atención media": "orange", "En tiempo": "green"}

datos = datos_visibles()
todos = datos["proyectos_todos"]
st.caption(f"Fuente: concentrados de proyectos de las PMs ({datos['fuentes']['proyectos']}). "
           "Foto actual del portafolio: no aplica el periodo ni las áreas de la barra lateral.")
if todos.empty:
    st.info("No hay proyectos visibles para tu usuario.", icon=":material/folder_off:")
    st.stop()

portafolios = sorted(todos["portafolio"].dropna().unique())
elegidos = st.pills("Portafolio", portafolios, default=portafolios, selection_mode="multi", key="proy_portafolio")
p = todos[todos["portafolio"].isin(elegidos or portafolios)]
asig = datos["asignaciones"][datos["asignaciones"]["proyecto_id"].isin(p["proyecto_id"])]
activos = p[p["activo"]]

with st.container(horizontal=True):
    st.metric("Total de proyectos", fmt_num(len(p)), border=True)
    for estado in ["Terminado", "En desarrollo", "En pruebas", "En espera"]:
        st.metric(estado if estado != "Terminado" else "Terminados", fmt_num((p["estado"] == estado).sum()), border=True)
    st.metric("Atrasados", fmt_num((p["semaforo"] == "Atención alta").sum()), border=True,
              help=f"En marcha y vencidos, o {UMBRAL_ALTO:.0%} o más por debajo del avance esperado")
st.caption(f"Avance promedio de los proyectos en marcha: **{fmt_pct(activos['avance'].mean())}** · "
           f"Requieren seguimiento (atención media): **{(p['semaforo'] == 'Atención media').sum()}**")

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.subheader("¿En qué etapa está cada proyecto?")
        etapas = p["estado"].value_counts().reindex(ESTADOS_PROYECTO).dropna().rename("proyectos").reset_index()
        st.altair_chart(
            alt.Chart(etapas).mark_bar(cornerRadiusEnd=3).encode(
                x=alt.X("proyectos:Q", title="Proyectos"),
                y=alt.Y("estado:N", sort=ESTADOS_PROYECTO, title=None),
                color=alt.Color("estado:N", scale=ESCALA_ESTADO, legend=None),
                tooltip=[alt.Tooltip("estado:N", title="Etapa"), alt.Tooltip("proyectos:Q", title="Proyectos")],
            ).properties(height=220),
            alt="Proyectos por etapa",
        )
with c2:
    with st.container(border=True, height="stretch"):
        st.subheader("Proyectos que requieren atención")
        st.caption(f"Atención alta: vencido o {UMBRAL_ALTO:.0%}+ debajo de lo esperado a hoy. "
                   f"Atención media: {UMBRAL_MEDIO:.0%}–{UMBRAL_ALTO:.0%} debajo.")
        alerta = p[p["semaforo"].isin(["Atención alta", "Atención media"])].sort_values(["semaforo", "brecha"])
        if alerta.empty:
            st.success("Todos los proyectos en marcha van en tiempo.", icon=":material/check_circle:")
        with st.container(height=420 if len(alerta) > 3 else "content"):
            for r in alerta.itertuples():
                with st.container(border=True):
                    with st.container(horizontal=True, vertical_alignment="center"):
                        st.markdown(f"**{r.proyecto}**")
                        st.badge(r.semaforo, color=COLOR_SEMAFORO[r.semaforo])
                    st.progress(float(r.avance), text=f"Avance {r.avance:.0%} · esperado {r.esperado:.0%}")
                    detalle = [f"Desarrollo: {r.desarrollo or '—'}"]
                    if pd.notna(r.fin):
                        detalle.append(f"Cierre {r.fin:%d/%m/%Y}")
                    if pd.notna(r.dias_restantes):
                        d = int(r.dias_restantes)
                        detalle.append(f"faltan {d} días" if d >= 0 else f"vencido hace {-d} días")
                    st.caption(" · ".join(detalle))
                    if r.situacion:
                        st.caption(str(r.situacion)[:300])

with st.container(border=True):
    st.subheader("Carga de trabajo por responsable")
    rol = st.segmented_control("Función", ROLES_PROYECTO, default="Desarrollo", required=True, key="proy_rol")
    carga = asig[asig["rol"] == rol].groupby(["colaborador", "estado"]).size().rename("proyectos").reset_index()
    if carga.empty:
        st.caption("Sin asignaciones para esta función.")
    else:
        orden = (carga.assign(act=carga["estado"].isin(ESTADOS_ACTIVOS) * carga["proyectos"])
                 .groupby("colaborador")[["act", "proyectos"]].sum().sort_values(["act", "proyectos"], ascending=False)
                 .index.tolist())
        st.altair_chart(
            alt.Chart(carga).mark_bar().encode(
                x=alt.X("sum(proyectos):Q", title="Proyectos"),
                y=alt.Y("colaborador:N", sort=orden, title=None),
                color=alt.Color("estado:N", scale=ESCALA_ESTADO, title="Etapa"),
                order=alt.Order("estado:N"),
                tooltip=[alt.Tooltip("colaborador:N", title="Persona"), alt.Tooltip("estado:N", title="Etapa"),
                         alt.Tooltip("proyectos:Q", title="Proyectos")],
            ).properties(height=max(160, 30 * len(orden))),
            alt=f"Proyectos por persona en la función {rol}, por etapa",
        )
        st.caption("Una persona puede estar en varios proyectos y un proyecto puede tener varios responsables.")

with st.container(border=True):
    st.subheader("Cronograma (Gantt)")
    vista = st.segmented_control("Mostrar", ["En marcha y en espera", "Todos"], default="En marcha y en espera",
                                 required=True, key="proy_gantt")
    g = p[p["inicio"].notna()].copy()
    if vista != "Todos":
        g = g[~g["estado"].isin(["Terminado", "Cancelado"])]
    hoy = pd.Timestamp(date.today())
    g["sin_fin"] = g["fin"].isna()
    g["fin_graf"] = g["fin"].fillna(pd.Series(hoy, index=g.index).where(g["inicio"] < hoy, g["inicio"] + pd.Timedelta(days=7)))
    g["avance_fin"] = g["inicio"] + (g["fin_graf"] - g["inicio"]) * g["avance"]
    g["periodo"] = g["inicio"].dt.strftime("%d/%m/%Y") + " → " + g["fin"].dt.strftime("%d/%m/%Y").fillna("sin fecha de cierre")
    if g.empty:
        st.caption("Sin proyectos con fecha de inicio.")
    else:
        orden_g = g.sort_values(["inicio", "fin_graf"])["proyecto"].tolist()
        base = alt.Chart(g).encode(
            y=alt.Y("proyecto:N", sort=orden_g, title=None, axis=alt.Axis(labelLimit=260)),
            tooltip=[alt.Tooltip("proyecto:N", title="Proyecto"), alt.Tooltip("estado:N", title="Etapa"),
                     alt.Tooltip("avance:Q", title="Avance", format=".0%"), alt.Tooltip("periodo:N", title="Fechas"),
                     alt.Tooltip("desarrollo:N", title="Desarrollo"), alt.Tooltip("semaforo:N", title="Semáforo")],
        )
        plan = base.mark_bar(opacity=0.25, cornerRadius=3).encode(
            x=alt.X("inicio:T", title=None, axis=alt.Axis(format="%b %Y")), x2="fin_graf:T",
            color=alt.Color("estado:N", scale=ESCALA_ESTADO, title="Etapa"),
            strokeDash=alt.condition("datum.sin_fin", alt.value([4, 3]), alt.value([0, 0])),
            stroke=alt.Color("estado:N", scale=ESCALA_ESTADO, legend=None),
        )
        hecho = base.mark_bar(cornerRadius=3).encode(x="inicio:T", x2="avance_fin:T",
                                                     color=alt.Color("estado:N", scale=ESCALA_ESTADO, legend=None))
        etiqueta = base.mark_text(align="left", dx=4, fontSize=11).encode(x="fin_graf:T",
                                                                          text=alt.Text("avance:Q", format=".0%"))
        corte = alt.Chart(pd.DataFrame({"hoy": [hoy]})).mark_rule(strokeDash=[4, 3], color="#64748B").encode(x="hoy:T")
        st.altair_chart((plan + hecho + etiqueta + corte).properties(height=max(200, 26 * len(g))),
                        alt="Diagrama de Gantt de los proyectos: inicio a cierre y avance")
        st.caption("Parte sólida: avance. Barras con borde punteado: sin fecha de cierre (se dibujan hasta hoy). "
                   "Línea punteada: hoy.")

with st.container(border=True):
    st.subheader("Detalle por proyecto")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        buscar = st.text_input("Buscar", placeholder="Proyecto, responsable, área solicitante…",
                               icon=":material/search:", key="proy_buscar")
        etapa = st.segmented_control("Etapa", ["Todos", "En marcha", "En espera", "Terminado"], default="Todos",
                                     required=True, key="proy_etapa")
    t = p.copy()
    if etapa == "En marcha":
        t = t[t["activo"]]
    elif etapa != "Todos":
        t = t[t["estado"] == etapa]
    if buscar:
        texto = t[["proyecto", "estado", "desarrollo", "base_datos", "coordinacion", "solicitante", "portafolio",
                   "situacion"]].fillna("").astype(str).agg(" ".join, axis=1)
        t = t[texto.str.contains(buscar, case=False, regex=False)]
    st.caption(f"Mostrando {len(t)} de {len(p)} proyectos")
    st.dataframe(
        t.sort_values("inicio"),
        hide_index=True,
        column_order=["proyecto", "estado", "semaforo", "avance", "desarrollo", "base_datos", "coordinacion",
                      "solicitante", "portafolio", "inicio", "fin", "situacion"],
        column_config={
            "proyecto": st.column_config.TextColumn("Proyecto", pinned=True),
            "estado": "Etapa",
            "semaforo": "Semáforo",
            "avance": st.column_config.ProgressColumn("Avance", format="percent", min_value=0, max_value=1),
            "desarrollo": "Desarrollo",
            "base_datos": "Base de datos",
            "coordinacion": "Coordinación",
            "solicitante": "Área solicitante",
            "portafolio": "Portafolio",
            "inicio": st.column_config.DateColumn("Inicio", format="DD/MM/YYYY"),
            "fin": st.column_config.DateColumn("Cierre", format="DD/MM/YYYY"),
            "situacion": st.column_config.TextColumn("Situación actual", width="large"),
        },
        alt="Detalle de proyectos con etapa, semáforo, avance y responsables",
    )
