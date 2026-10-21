"""Indicadores mensuales por persona (ficha individual y comparativo de personas).

Ignora los filtros de periodo/área de la barra lateral: siempre es el año completo de la persona.
Tickets cerrados se cuentan en el mes en que se resolvieron.
"""

from datetime import date

import pandas as pd

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
         "Octubre", "Noviembre", "Diciembre"]

# indicador -> (columna, formato st.column_config, mayor es mejor)
INDICADORES_PERSONA = {
    "Tickets cerrados": ("cerrados", "%d", True),
    "Cumplimiento SLA": ("pct_sla", "percent", True),
    "Resolución (días)": ("dias_resolucion", "%.1f", False),
    "Asistencia": ("pct_asistencia", "percent", True),
    "Retardos": ("retardos", "%d", False),
    "Faltas": ("faltas", "%d", False),
    "Días de vacaciones": ("vacaciones", "%d", None),
}


def años_disponibles(datos: dict) -> list[int]:
    años = set(datos["asistencias"]["fecha"].dt.year.dropna().astype(int))
    años |= set(datos["tickets"]["fecha_resuelto"].dt.year.dropna().astype(int))
    return sorted(años, reverse=True) or [date.today().year]


def mensual(datos: dict, ids: list[str], año: int) -> pd.DataFrame:
    """Una fila por persona y mes del año (hasta el mes actual si es el año en curso)."""
    hoy = date.today()
    ultimo_mes = hoy.month if año == hoy.year else 12
    nombres = datos["colaboradores"].set_index("id")["nombre"]
    base = pd.MultiIndex.from_product([ids, range(1, ultimo_mes + 1)], names=["colaborador_id", "mes"])

    t = datos["tickets"]
    cerr = t[(t["estado"] == "cerrado") & t["colaborador_id"].isin(ids) & (t["fecha_resuelto"].dt.year == año)]
    g_t = cerr.groupby(["colaborador_id", cerr["fecha_resuelto"].dt.month.rename("mes")])

    a = datos["asistencias"]
    a = a[a["colaborador_id"].isin(ids) & (a["fecha"].dt.year == año)]
    g_a = a.groupby(["colaborador_id", a["fecha"].dt.month.rename("mes")])
    cuenta = lambda estatus: g_a["estatus"].apply(lambda s: (s == estatus).sum())  # noqa: E731

    m = pd.DataFrame(
        {
            "cerrados": g_t.size(),
            "sla_ok": g_t["cumple_sla"].sum(),
            "dias_resolucion": g_t["dias_resolucion"].mean(),
            "presentes": g_a["presente"].sum(),
            "laborables": g_a["laborable"].sum(),
            "retardos": g_a["retardo"].sum(),
            "faltas": cuenta("falta"),
            "vacaciones": cuenta("vacaciones"),
            "incapacidad": cuenta("incapacidad"),
            "sin_salida": g_a["sin_salida"].sum(),
        }
    ).reindex(base)
    conteos = ["cerrados", "sla_ok", "presentes", "laborables", "retardos", "faltas", "vacaciones", "incapacidad",
               "sin_salida"]
    m[conteos] = m[conteos].fillna(0).astype(int)
    m["pct_sla"] = m["sla_ok"] / m["cerrados"].where(m["cerrados"] > 0)
    m["pct_asistencia"] = m["presentes"] / m["laborables"].where(m["laborables"] > 0)
    m = m.reset_index()
    m["colaborador"] = m["colaborador_id"].map(nombres)
    m["mes_nombre"] = m["mes"].map(lambda x: MESES[x])
    m["mes_fecha"] = pd.to_datetime({"year": año, "month": m["mes"], "day": 1})
    return m


def totales(m: pd.DataFrame) -> pd.DataFrame:
    """Año completo por persona, con porcentajes ponderados (no promedio de promedios)."""
    g = m.groupby(["colaborador_id", "colaborador"])
    tot = g[["cerrados", "sla_ok", "presentes", "laborables", "retardos", "faltas", "vacaciones", "incapacidad",
             "sin_salida"]].sum()
    # Días de resolución: promedio ponderado por tickets cerrados de cada mes
    peso = m["dias_resolucion"].fillna(0) * m["cerrados"]
    tot["dias_resolucion"] = peso.groupby([m["colaborador_id"], m["colaborador"]]).sum() / tot["cerrados"].where(
        tot["cerrados"] > 0)
    tot["pct_sla"] = tot["sla_ok"] / tot["cerrados"].where(tot["cerrados"] > 0)
    tot["pct_asistencia"] = tot["presentes"] / tot["laborables"].where(tot["laborables"] > 0)
    tot["meses_con_vacaciones"] = g.apply(
        lambda x: ", ".join(f"{r.mes_nombre} ({r.vacaciones})" for r in x.itertuples() if r.vacaciones > 0) or "—",
        include_groups=False,
    )
    return tot.reset_index()
