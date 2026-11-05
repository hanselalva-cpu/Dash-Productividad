"""Calendario mensual en HTML: en cada día, quién está de vacaciones."""

import calendar
import html
from datetime import date

import pandas as pd

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
         "Octubre", "Noviembre", "Diciembre"]
DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# Mismo orden de colores categóricos que .streamlit/config.toml
_COLORES = {
    "light": ["#1D4ED8", "#059669", "#7C3AED", "#DC2626", "#D97706", "#0284C7", "#64748B", "#EA580C"],
    "dark": ["#60A5FA", "#34D399", "#A78BFA", "#F87171", "#FBBF24", "#38BDF8", "#94A3B8", "#FB923C"],
}
_TEMA = {
    "light": {"texto": "#0F172A", "suave": "#64748B", "borde": "#CBD5E1", "finde": "#F1F5F9", "hoy": "#1D4ED8"},
    "dark": {"texto": "#F1F5F9", "suave": "#94A3B8", "borde": "#334155", "finde": "#1E293B", "hoy": "#60A5FA"},
}


def nombre_corto(nombre: str) -> str:
    """'Perez Lopez Juan' -> 'Juan Perez' (el listado viene como apellidos + nombres)."""
    partes = str(nombre).split()
    return f"{partes[-1]} {partes[0]}" if len(partes) >= 3 else str(nombre)


def colores_por_area(areas: list[str], tema: str) -> dict[str, str]:
    paleta = _COLORES.get(tema, _COLORES["light"])
    return {a: paleta[i % len(paleta)] for i, a in enumerate(areas)}


def calendario_html(año: int, mes: int, dias: pd.DataFrame, colores: dict[str, str], tema: str = "light") -> str:
    """`dias`: columnas fecha (datetime), colaborador, area; una fila por persona y día de vacaciones.

    Días posteriores a hoy (vacaciones programadas) se dibujan con borde punteado y fondo claro."""
    t = _TEMA.get(tema, _TEMA["light"])
    por_dia = {
        d.date(): g.sort_values(["area", "colaborador"]) for d, g in dias.groupby(dias["fecha"].dt.normalize())
    }
    hoy = date.today()

    celdas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(año, mes):
        fila = []
        for i, dia in enumerate(semana):
            fuera = dia.month != mes
            fondo = t["finde"] if i >= 5 else "transparent"
            numero_estilo = f"color:{t['hoy']};font-weight:700;" if dia == hoy else ""
            chips = ""
            if not fuera and dia in por_dia:
                futuro = dia > hoy
                for _, r in por_dia[dia].iterrows():
                    c = colores.get(r["area"], t["suave"])
                    estilo = (f"border:1px dashed {c};border-left:3px dashed {c};background:{c}0d;" if futuro
                              else f"border-left:3px solid {c};background:{c}22;")
                    titulo = f"{r['colaborador']} · {r['area']}" + (" · programada" if futuro else "")
                    chips += (
                        f'<div class="chip" title="{html.escape(titulo)}" style="{estilo}">'
                        f"{html.escape(nombre_corto(r['colaborador']))}</div>"
                    )
            fila.append(
                f'<td style="background:{fondo};{"opacity:.35;" if fuera else ""}">'
                f'<div class="num" style="{numero_estilo}">{dia.day}</div>{chips}</td>'
            )
        celdas.append("<tr>" + "".join(fila) + "</tr>")

    encabezado = "".join(f"<th>{d}</th>" for d in DIAS)
    return f"""
<style>
.cal-vac {{ width:100%; border-collapse:collapse; table-layout:fixed; font-size:12px; color:{t['texto']}; }}
.cal-vac th {{ padding:6px 4px; font-weight:600; color:{t['suave']}; border-bottom:1px solid {t['borde']}; }}
.cal-vac td {{ vertical-align:top; height:84px; padding:4px; border:1px solid {t['borde']}; }}
.cal-vac .num {{ font-size:11px; color:{t['suave']}; margin-bottom:3px; }}
.cal-vac .chip {{ padding:1px 5px; margin-bottom:2px; border-radius:3px; white-space:nowrap; overflow:hidden;
                  text-overflow:ellipsis; line-height:1.5; }}
</style>
<table class="cal-vac"><thead><tr>{encabezado}</tr></thead><tbody>{''.join(celdas)}</tbody></table>
"""
