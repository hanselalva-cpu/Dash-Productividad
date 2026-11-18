"""Calendario ejecutivo con solo las vacaciones de una persona, directo del sistema de incidencias.

Uso (desde la raíz del proyecto):
    python -m tools.vacaciones_persona --id E012345 --desde 2026-11 --hasta 2027-02
    python -m tools.vacaciones_persona --id E012345 --desde 2026-11 --hasta 2027-02 --esperado 2026-11-23:2026-11-27

Genera entregables/Vacaciones_<id>_<desde>_<hasta>.html y .png (captura con Edge) y escribe en
logs/vacaciones_revision.log los periodos encontrados y, con --esperado, cuáles faltan en el sistema.
"""

import argparse
import calendar
import os
import subprocess
from datetime import date, datetime

import pandas as pd
from dotenv import load_dotenv

from etl.asistencias_to_supabase import BASE, SQL
from etl.servicedesk_to_supabase import _ejecutar, conectar_sql

NOMBRE_MES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre",
              "Octubre", "Noviembre", "Diciembre"]
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def meses(desde: str, hasta: str) -> list[tuple[int, int]]:
    return [(p.year, p.month) for p in pd.period_range(desde, hasta, freq="M")]


def leer(id_empleado: str, lista_meses: list[tuple[int, int]]) -> tuple[set, set]:
    with conectar_sql(BASE) as cn:
        df = pd.concat(_ejecutar(cn, SQL, [date(a, m, 1), date(a, m, calendar.monthrange(a, m)[1])])
                       for a, m in lista_meses)
    p = df[df["Personal"] == id_empleado].copy()
    p["Fecha"] = pd.to_datetime(p["Fecha"]).dt.date
    vac = set(p.loc[p["Incidencia"].astype(str).str.startswith("VAC"), "Fecha"])
    festivos = {f for f in p.loc[p["Incidencia"].isin(["DOL", "DOG"]), "Fecha"] if f.weekday() < 5}
    return vac, festivos


def periodos(vac: set, festivos: set) -> list[list[date]]:
    """Días consecutivos; fines de semana y festivos no cortan el periodo."""
    salida = []
    for d in sorted(vac):
        if salida:
            hueco = pd.bdate_range(salida[-1][-1], d)[1:-1]
            if all(h.date() in festivos for h in hueco):
                salida[-1].append(d)
                continue
        salida.append([d])
    return salida


def regreso(d: date, vac: set, festivos: set) -> date:
    for x in pd.bdate_range(d, periods=15)[1:]:
        if x.date() not in vac and x.date() not in festivos:
            return x.date()
    return d


def fmt(d: date) -> str:
    return f"{d.day} de {NOMBRE_MES[d.month].lower()}"


def html(nombre: str, lista_meses, vac, festivos, pers) -> str:
    filas = "".join(
        f"<tr><td>{fmt(p[0])} al {fmt(p[-1])}</td><td class='n'>{len(p)}</td><td>{fmt(regreso(p[-1], vac, festivos))}</td></tr>"
        for p in pers
    ) or "<tr><td colspan='3'>Sin vacaciones registradas en el periodo</td></tr>"

    def mes_html(año, mes):
        filas_cal = []
        for semana in calendar.Calendar(0).monthdatescalendar(año, mes):
            celdas = []
            for i, d in enumerate(semana):
                if d.month != mes:
                    celdas.append("<td class='fuera'></td>")
                    continue
                clase = "vac" if d in vac else "fest" if d in festivos else "finde" if i >= 5 else ""
                celdas.append(f"<td class='{clase}'>{d.day}</td>")
            filas_cal.append("<tr>" + "".join(celdas) + "</tr>")
        n = sum(1 for d in vac if d.year == año and d.month == mes)
        sub = f"{n} día{'s' if n != 1 else ''} de vacaciones" if n else "Sin vacaciones"
        return (f"<div class='mes'><h3>{NOMBRE_MES[mes]} {año}</h3><p class='sub {'' if n else 'cero'}'>{sub}</p>"
                "<table class='cal'><tr>" + "".join(f"<th>{x}</th>" for x in "LMMJVSD") + "</tr>"
                + "".join(filas_cal) + "</table></div>")

    rango = f"{NOMBRE_MES[lista_meses[0][1]].lower()} {lista_meses[0][0]} – {NOMBRE_MES[lista_meses[-1][1]].lower()} {lista_meses[-1][0]}"
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Vacaciones programadas</title>
<style>
body {{ margin:0; background:#fff; font-family:Arial, Helvetica, sans-serif; color:#0F172A; }}
.hoja {{ width:960px; padding:32px 36px; box-sizing:border-box; }}
h1 {{ font-size:22px; margin:0 0 4px; color:#1F3864; }}
.meta {{ font-size:13px; color:#64748B; margin:0 0 20px; }}
.resumen {{ display:flex; gap:16px; margin-bottom:22px; }}
.kpi {{ border:1px solid #CBD5E1; border-top:3px solid #1D4ED8; border-radius:6px; padding:10px 16px; min-width:150px; }}
.kpi b {{ display:block; font-size:26px; color:#1D4ED8; }}
.kpi span {{ font-size:12px; color:#64748B; }}
table.per {{ border-collapse:collapse; font-size:13px; margin-bottom:24px; width:100%; }}
table.per th {{ text-align:left; background:#1F3864; color:#fff; padding:7px 10px; font-weight:600; }}
table.per td {{ padding:7px 10px; border-bottom:1px solid #E2E8F0; }}
table.per td.n {{ text-align:center; }}
.meses {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:18px; }}
.mes h3 {{ margin:0; font-size:15px; }}
.sub {{ margin:2px 0 8px; font-size:12px; color:#1D4ED8; font-weight:600; }}
.sub.cero {{ color:#94A3B8; font-weight:400; }}
table.cal {{ border-collapse:collapse; width:100%; font-size:12px; table-layout:fixed; }}
table.cal th {{ color:#64748B; font-weight:600; padding:3px 0; }}
table.cal td {{ text-align:center; padding:5px 0; border:1px solid #F1F5F9; }}
td.finde {{ color:#94A3B8; background:#F8FAFC; }}
td.vac {{ background:#1D4ED8; color:#fff; font-weight:700; }}
td.fest {{ background:#FEF3C7; color:#92400E; }}
td.fuera {{ border:none; }}
.leyenda {{ margin-top:16px; font-size:12px; color:#475569; display:flex; gap:18px; }}
.leyenda i {{ display:inline-block; width:12px; height:12px; border-radius:2px; vertical-align:-2px; margin-right:5px; }}
</style></head><body><div class="hoja">
<h1>Vacaciones programadas · {nombre}</h1>
<p class="meta">{rango[0].upper() + rango[1:]} · Fuente: sistema de incidencias de RH, al {date.today():%d/%m/%Y}</p>
<div class="resumen">
  <div class="kpi"><b>{len(vac)}</b><span>días hábiles de vacaciones</span></div>
  <div class="kpi"><b>{len(pers)}</b><span>periodo{'s' if len(pers) != 1 else ''}</span></div>
</div>
<table class="per"><tr><th>Periodo</th><th style="text-align:center">Días hábiles</th><th>Regreso a labores</th></tr>{filas}</table>
<div class="meses">{''.join(mes_html(a, m) for a, m in lista_meses)}</div>
<div class="leyenda"><span><i style="background:#1D4ED8"></i>Vacaciones</span>
<span><i style="background:#FEF3C7;border:1px solid #F59E0B"></i>Día festivo / descanso</span>
<span><i style="background:#F8FAFC;border:1px solid #CBD5E1"></i>Fin de semana</span></div>
</div></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--id", required=True, help="id_empleado")
    parser.add_argument("--desde", required=True, help="Mes inicial YYYY-MM")
    parser.add_argument("--hasta", required=True, help="Mes final YYYY-MM")
    parser.add_argument("--esperado", nargs="*", default=[], help="Periodos aprobados AAAA-MM-DD:AAAA-MM-DD a verificar")
    args = parser.parse_args()
    load_dotenv()

    personal = pd.read_csv("data/personal.csv", dtype=str).set_index("id_empleado")
    partes = str(personal.loc[args.id, "nombre"]).title().split() if args.id in personal.index else [args.id]
    nombre = " ".join(partes[2:] + partes[:2]) if len(partes) >= 3 else " ".join(partes)  # APELLIDOS NOMBRES -> Nombres Apellidos

    lista = meses(args.desde, args.hasta)
    vac, festivos = leer(args.id, lista)
    pers = periodos(vac, festivos)

    os.makedirs("entregables", exist_ok=True)
    base = os.path.abspath(f"entregables/Vacaciones_{args.id}_{args.desde}_{args.hasta}")
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(html(nombre, lista, vac, festivos, pers))
    edge = next((e for e in EDGE if os.path.exists(e)), None)
    if edge:
        subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=960,720",
                        f"--screenshot={base}.png", "file:///" + (base + ".html").replace("\\", "/")],
                       capture_output=True, timeout=60)

    lineas = [f"===== {datetime.now():%Y-%m-%d %H:%M} · {args.id} · {args.desde} a {args.hasta}",
              f"  {len(vac)} días en {len(pers)} periodos: "
              + "; ".join(f"{p[0]:%d/%m/%Y}-{p[-1]:%d/%m/%Y}" for p in pers)]
    for e in args.esperado:
        ini, fin = (date.fromisoformat(x) for x in e.split(":"))
        habiles = [d.date() for d in pd.bdate_range(ini, fin) if d.date() not in festivos]
        faltan = [d for d in habiles if d not in vac]
        estado = "OK, ya registrado" if not faltan else f"FALTAN {len(faltan)} de {len(habiles)} días"
        lineas.append(f"  esperado {ini:%d/%m/%Y}-{fin:%d/%m/%Y}: {estado}")
    os.makedirs("logs", exist_ok=True)
    with open("logs/vacaciones_revision.log", "a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    print("\n".join(lineas))
    print(f"  -> {base}.png")


if __name__ == "__main__":
    main()
