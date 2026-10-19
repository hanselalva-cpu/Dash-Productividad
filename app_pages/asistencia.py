import calendar
from datetime import date

import pandas as pd
import streamlit as st

from tablero.calendario import MESES, calendario_html, colores_por_area
from tablero.config import AREAS, TOLERANCIA_RETARDO_MIN
from tablero.data import datos_visibles, filtrar, periodo_anterior
from tablero.metrics import delta, fmt_num, fmt_pct, kpis

inicio, fin, areas, edificios = st.session_state.filtro
datos = datos_visibles()
f = filtrar(datos, inicio, fin, areas, edificios)
k = kpis(f)
k0 = kpis(filtrar(datos, *periodo_anterior(inicio, fin), areas, edificios))
a = f["asistencias"]

with st.container(horizontal=True):
    st.metric("Asistencia", fmt_pct(k["pct_asistencia"]), delta(k["pct_asistencia"], k0["pct_asistencia"], pct=True),
              border=True, help="Días laborados ÷ días laborables (sin descansos, vacaciones ni incapacidades)")
    st.metric("Faltas", fmt_num(k["faltas"]), delta(k["faltas"], k0["faltas"]), delta_color="inverse", border=True)
    st.metric("Retardos", fmt_num(k["retardos"]), delta(k["retardos"], k0["retardos"]), delta_color="inverse",
              border=True, help=f"Entrada más de {TOLERANCIA_RETARDO_MIN} min después del inicio de jornada")
    st.metric("Minutos de retardo (mediana)", fmt_num(k["min_retardo_mediana"], 0),
              delta(k["min_retardo_mediana"], k0["min_retardo_mediana"]), delta_color="inverse", border=True)
    st.metric("Días de vacaciones", fmt_num(k["dias_vacaciones"]), delta(k["dias_vacaciones"], k0["dias_vacaciones"]),
              delta_color="off", border=True)
    st.metric("Días sin checada de salida", fmt_num(k["sin_salida"]), delta(k["sin_salida"], k0["sin_salida"]),
              delta_color="inverse", border=True)

col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        st.subheader("Retardos por semana")
        semanal = a[a["retardo"]].groupby(["semana", "area"]).size().rename("retardos").reset_index()
        st.bar_chart(semanal, x="semana", y="retardos", color="area", x_label="", y_label="Retardos",
                     alt="Retardos por semana y área")
with col2:
    with st.container(border=True):
        st.subheader("Estatus de días laborables por área")
        estatus = a[a["laborable"]].groupby(["area", "estatus"]).size().rename("días").reset_index()
        st.bar_chart(estatus, x="area", y="días", color="estatus", stack="normalize", x_label="", y_label="Proporción",
                     alt="Distribución de asistencia, retardos y faltas por área")

with st.container(border=True):
    st.subheader("Asistencia por colaborador")
    por_persona = (
        a.groupby(["colaborador", "area"])
        .agg(
            laborables=("laborable", "sum"),
            presentes=("presente", "sum"),
            retardos=("retardo", "sum"),
            minutos=("minutos_retardo", "median"),
            faltas=("estatus", lambda s: (s == "falta").sum()),
            vacaciones=("estatus", lambda s: (s == "vacaciones").sum()),
            incapacidad=("estatus", lambda s: (s == "incapacidad").sum()),
            sin_salida=("sin_salida", "sum"),
        )
        .reset_index()
    )
    por_persona["pct_asistencia"] = por_persona["presentes"] / por_persona["laborables"].where(por_persona["laborables"] > 0)
    por_persona = por_persona.sort_values(["retardos", "faltas"], ascending=False).reset_index(drop=True)
    seleccion = st.dataframe(
        por_persona,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="asistencia_persona",
        column_order=["colaborador", "area", "pct_asistencia", "laborables", "retardos", "minutos", "faltas",
                      "vacaciones", "incapacidad", "sin_salida"],
        column_config={
            "colaborador": "Colaborador",
            "area": "Área",
            "pct_asistencia": st.column_config.ProgressColumn("Asistencia", format="percent", min_value=0, max_value=1),
            "laborables": st.column_config.NumberColumn("Días laborables"),
            "retardos": st.column_config.NumberColumn("Retardos"),
            "minutos": st.column_config.NumberColumn("Min. retardo (mediana)", format="%.0f"),
            "faltas": st.column_config.NumberColumn("Faltas"),
            "vacaciones": st.column_config.NumberColumn("Vacaciones"),
            "incapacidad": st.column_config.NumberColumn("Incapacidad"),
            "sin_salida": st.column_config.NumberColumn("Sin checada salida"),
        },
        alt="Asistencia, retardos y faltas por colaborador",
    )
    st.caption("Selecciona una fila para ver el detalle día por día de esa persona.")

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
TIPOS = {
    "Faltas": a["estatus"] == "falta",
    "Retardos": a["retardo"],
    "Incapacidades": a["estatus"] == "incapacidad",
    "Vacaciones": a["estatus"] == "vacaciones",
    "Sin checada de salida": a["sin_salida"],
}
with st.container(border=True):
    st.subheader("Detalle por día")
    filas_sel = seleccion.selection.rows
    persona = por_persona.loc[filas_sel[0], "colaborador"] if filas_sel else None
    with st.container(horizontal=True, vertical_alignment="center"):
        tipos = st.pills("Tipo", list(TIPOS), default=["Faltas"], selection_mode="multi", key="detalle_tipo")
        if persona:
            st.badge(f"Persona: {persona}", icon=":material/person:", color="blue")
    if not tipos:
        st.info("Elige al menos un tipo.", icon=":material/filter_alt:")
    else:
        mascara = pd.concat([TIPOS[t] for t in tipos], axis=1).any(axis=1)
        detalle = a[mascara]
        if persona:
            detalle = detalle[detalle["colaborador"] == persona]
        nombres_tipo = {t: m for t, m in TIPOS.items() if t in tipos}
        detalle = detalle.assign(
            tipo=lambda df: df.index.to_series().map(
                lambda i: ", ".join(t for t, m in nombres_tipo.items() if m.get(i, False))
            )
        )
        detalle = detalle.assign(dia=detalle["fecha"].dt.dayofweek.map(dict(enumerate(DIAS_SEMANA))))
        st.caption(f"{len(detalle)} día{'s' if len(detalle) != 1 else ''}")
        st.dataframe(
            detalle.sort_values(["fecha", "colaborador"], ascending=[False, True])[
                ["fecha", "dia", "colaborador", "area", "tipo", "incidencia", "descripcion", "inicio_jornada", "entrada",
                 "salida", "minutos_tarde", "comentario"]
            ],
            hide_index=True,
            column_config={
                "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "dia": "Día",
                "colaborador": "Colaborador",
                "area": "Área",
                "tipo": "Tipo",
                "incidencia": "Código",
                "descripcion": "Descripción",
                "inicio_jornada": "Inicio jornada",
                "entrada": "Entrada",
                "salida": "Salida",
                "minutos_tarde": st.column_config.NumberColumn("Min. tarde", format="%.0f"),
                "comentario": "Comentario",
            },
            alt="Detalle día por día de faltas, retardos, incapacidades y vacaciones",
        )

with st.container(border=True):
    st.subheader("Validación de checadas")
    r_sistema = int((a["incidencia"] == "R").sum())
    st.caption(
        f"El sistema de incidencias marcó {r_sistema:,} retardos en el periodo (desde el primer minuto); "
        f"con la tolerancia de {TOLERANCIA_RETARDO_MIN} min quedan {k['retardos']:,}."
    )
    problemas = a[a["sin_entrada"] | a["sin_salida"] | a["sin_horario"] | a["una_checada"]
                  | (a["estatus"] == "sin_registro")].copy()
    problemas["problema"] = (
        problemas["sin_entrada"].map({True: "Sin entrada · ", False: ""})
        + problemas["sin_salida"].map({True: "Sin salida · ", False: ""})
        + problemas["sin_horario"].map({True: "Sin horario · ", False: ""})
        + problemas["una_checada"].map({True: "Una sola checada · ", False: ""})
        + (problemas["estatus"] == "sin_registro").map({True: "Sin incidencia · ", False: ""})
    ).str.rstrip(" · ")
    habitual = a[a["presente"] & ~a["una_checada"]].groupby("colaborador")["minutos_tarde"].agg(["median", "size"])
    habitual = habitual[(habitual["median"] > 120) & (habitual["size"] >= 5)]
    if not habitual.empty:
        st.warning(
            ", ".join(f"{n} (~{m / 60:.1f} h tarde)" for n, m in habitual["median"].items()),
            title="Llegan tarde casi siempre a la misma hora: revisar su horario en el sistema de incidencias",
            icon=":material/schedule:",
        )
    if problemas.empty:
        st.success("Todas las checadas del periodo están completas.", icon=":material/check_circle:")
    else:
        st.dataframe(
            problemas.sort_values(["fecha", "colaborador"], ascending=[False, True])[
                ["fecha", "colaborador", "area", "problema", "incidencia", "inicio_jornada", "entrada", "salida",
             "minutos_tarde"]
            ],
            hide_index=True,
            height=300,
            column_config={
                "fecha": st.column_config.DateColumn("Fecha", format="DD/MM/YYYY"),
                "colaborador": "Colaborador",
                "area": "Área",
                "problema": "Problema",
                "incidencia": "Incidencia",
                "inicio_jornada": "Inicio jornada",
                "entrada": "Entrada",
                "salida": "Salida",
                "minutos_tarde": st.column_config.NumberColumn("Min. tarde", format="%.0f"),
            },
            alt="Días con checadas incompletas",
        )

with st.container(border=True):
    st.subheader("Calendario de vacaciones")
    meses = {f"{m.year}-{m.month:02d}": f"{MESES[m.month]} {m.year}" for m in pd.period_range(inicio, fin, freq="M")}
    claves = list(meses)
    if len(claves) == 1:
        clave = claves[0]
    elif len(claves) <= 6:
        clave = st.segmented_control("Mes", claves, default=claves[-1], format_func=meses.get, required=True,
                                     key="vac_mes")
    else:
        clave = st.selectbox("Mes", claves, index=len(claves) - 1, format_func=meses.get, key="vac_mes_lista")
    if clave not in meses:
        clave = claves[-1]
    año, mes = map(int, clave.split("-"))

    fm = filtrar(datos, date(año, mes, 1), date(año, mes, calendar.monthrange(año, mes)[1]), areas, edificios)
    dias_vac = fm["asistencias"][fm["asistencias"]["estatus"] == "vacaciones"]
    tema = st.context.theme.type or "light"
    colores = colores_por_area(AREAS, tema)

    if dias_vac.empty:
        st.info(f"Nadie tomó vacaciones en {meses[clave]}.", icon=":material/beach_access:")
    else:
        resumen = dias_vac.groupby("area").agg(personas=("colaborador_id", "nunique"), dias=("fecha", "size"))
        leyenda = " ".join(
            f'<span style="display:inline-block;margin:0 12px 4px 0;font-size:12px;">'
            f'<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:{colores[a]};'
            f'margin-right:5px;"></span>{a}: {r.personas} persona{"s" if r.personas != 1 else ""} · {r.dias} días</span>'
            for a, r in resumen.reindex([a for a in AREAS if a in resumen.index]).iterrows()
        )
        st.html(f"<div>{leyenda}</div>" + calendario_html(año, mes, dias_vac, colores, tema))
        st.caption("Pasa el cursor sobre un nombre para ver el nombre completo y el área.")

    with st.expander("Detalle de periodos de vacaciones", icon=":material/table_rows:"):
        tomadas_año = (
            datos["asistencias"][(datos["asistencias"]["estatus"] == "vacaciones")
                                 & (datos["asistencias"]["fecha"].dt.year == date.today().year)]
            .groupby("colaborador_id").size()
        )
        v = f["vacaciones"].assign(dias_año=lambda df: df["colaborador_id"].map(tomadas_año).fillna(0).astype(int))
        st.dataframe(
            v.sort_values("fecha_inicio", ascending=False)[["colaborador", "area", "fecha_inicio", "fecha_fin", "dias",
                                                            "dias_año"]],
            hide_index=True,
            column_config={
                "colaborador": "Colaborador",
                "area": "Área",
                "fecha_inicio": st.column_config.DateColumn("Desde", format="DD/MM/YYYY"),
                "fecha_fin": st.column_config.DateColumn("Hasta", format="DD/MM/YYYY"),
                "dias": st.column_config.NumberColumn("Días"),
                "dias_año": st.column_config.NumberColumn(f"Días tomados {date.today().year}"),
            },
            alt="Periodos de vacaciones en el periodo seleccionado",
        )
