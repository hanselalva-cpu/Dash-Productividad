"""Cálculo de KPIs sobre datos ya filtrados (ver tablero.data.filtrar)."""

import numpy as np
import pandas as pd


def _div(a: float, b: float) -> float:
    return a / b if b else np.nan


def kpis(f: dict[str, pd.DataFrame]) -> dict[str, float]:
    t, p, a = f["tickets"], f["proyectos"], f["asistencias"]
    cerrados = t[t["estado"] == "cerrado"]
    personas = len(f["colaboradores"])
    return {
        # Tickets / tareas
        "creados": len(t),
        "cerrados": len(cerrados),
        "backlog": len(f["backlog"]),
        "dias_resolucion": cerrados["dias_resolucion"].mean(),
        "pct_sla": cerrados["cumple_sla"].mean(),
        # Productividad
        "personas": personas,
        "cerrados_por_persona": _div(len(cerrados), personas),
        # Proyectos
        "proyectos": len(p),
        "pct_proyectos_a_tiempo": 1 - p["retrasado"].mean() if len(p) else np.nan,
        # Calidad
        "pct_incidentes": _div((t["categoria"] == "Incidente").sum(), len(t)),
        "pct_cancelados": _div((t["estado"] == "cancelado").sum(), len(t)),
        "pct_sin_categoria": _div((t["categoria"] == "Sin Categoria").sum(), len(t)),
        # Asistencia
        "pct_asistencia": _div(a["presente"].sum(), a["laborable"].sum()),
        "faltas": int((a["estatus"] == "falta").sum()),
        "retardos": int(a["retardo"].sum()),
        "min_retardo_mediana": a.loc[a["retardo"], "minutos_retardo"].median(),
        "dias_vacaciones": int((a["estatus"] == "vacaciones").sum()),
        "incapacidades": int((a["estatus"] == "incapacidad").sum()),
        "sin_salida": int(a["sin_salida"].sum()),
        "sin_entrada": int(a["sin_entrada"].sum()),
        "una_checada": int(a["una_checada"].sum()),
    }


def resumen_por(f: dict[str, pd.DataFrame], clave: str) -> pd.DataFrame:
    """Scorecard agrupado por 'area' o 'colaborador_id'."""
    t, a = f["tickets"], f["asistencias"]
    cerrados = t[t["estado"] == "cerrado"]

    g_t = t.groupby(clave)
    g_cerr = cerrados.groupby(clave)
    g_asis = a.groupby(clave)
    tabla = pd.DataFrame(
        {
            "creados": g_t.size(),
            "cerrados": g_cerr.size(),
            "backlog": f["backlog"].groupby(clave).size(),
            "dias_resolucion": g_cerr["dias_resolucion"].mean(),
            "pct_sla": g_cerr["cumple_sla"].mean(),
            "pct_incidentes": g_t["categoria"].apply(lambda s: (s == "Incidente").mean()),
            "pct_cancelados": g_t["estado"].apply(lambda s: (s == "cancelado").mean()),
            "pct_asistencia": g_asis["presente"].sum() / g_asis["laborable"].sum().replace(0, float("nan")),
            "faltas": a[a["estatus"] == "falta"].groupby(clave).size(),
            "retardos": g_asis["retardo"].sum(),
            "dias_vacaciones": a[a["estatus"] == "vacaciones"].groupby(clave).size(),
            "sin_salida": g_asis["sin_salida"].sum(),
        }
    )
    if clave == "area":
        p = f["proyectos"]
        tabla["proyectos"] = p.groupby("area").size()
        tabla["pct_proyectos_a_tiempo"] = 1 - p.groupby("area")["retrasado"].mean()
        tabla["personas"] = f["colaboradores"].groupby("area").size()
        tabla["cerrados_por_persona"] = tabla["cerrados"] / tabla["personas"]

    conteos = ["creados", "cerrados", "backlog", "faltas", "retardos", "dias_vacaciones", "sin_salida", "proyectos",
               "personas"]
    for c in conteos:
        if c in tabla:
            tabla[c] = tabla[c].fillna(0).astype(int)
    return tabla


def delta(actual: float, anterior: float, pct: bool = False) -> float | str | None:
    """Delta para st.metric: puntos porcentuales si pct, si no diferencia absoluta."""
    if pd.isna(actual) or pd.isna(anterior):
        return None
    diff = actual - anterior
    if pct:
        return f"{diff * 100:+.1f} pp" if round(diff * 100, 1) else 0
    return round(diff, 1) if diff else 0


def fmt_pct(x: float) -> str:
    return "—" if pd.isna(x) else f"{x:.0%}"


def fmt_num(x: float, dec: int = 0) -> str:
    return "—" if pd.isna(x) else f"{x:,.{dec}f}"
