"""Proyectos de los concentrados de las PMs: semáforo de cumplimiento, responsables y áreas.

Semáforo (proyectos en marcha con inicio y fin): avance esperado = días transcurridos ÷ días planeados.
Atención alta: ya venció sin terminar o va UMBRAL_ALTO o más por debajo; atención media: UMBRAL_MEDIO o más.
El área de un proyecto son las áreas de las personas asignadas (un proyecto puede contar en varias).
"""

from datetime import date

import pandas as pd

from tablero.config import AREAS

COLUMNAS_PROYECTOS = [
    "proyecto_id", "portafolio", "portafolio_id", "proyecto", "objetivo", "estado", "estado_origen", "avance", "inicio", "fin",
    "solicitante", "responsables_texto", "situacion",
]
COLUMNAS_ASIGNACIONES = ["proyecto_id", "persona", "id_empleado", "rol"]
ESTADOS_PROYECTO = ["En desarrollo", "En pruebas", "En espera", "Terminado", "Cancelado"]
ESTADOS_ACTIVOS = ["En desarrollo", "En pruebas"]
ROLES_PROYECTO = ["Desarrollo", "Base de datos", "Coordinación", "Command center"]
SEMAFOROS = ["Atención alta", "Atención media", "En tiempo", "Sin fecha de cierre"]
UMBRAL_ALTO, UMBRAL_MEDIO = 0.30, 0.15


def vacios() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.DataFrame(columns=COLUMNAS_PROYECTOS), pd.DataFrame(columns=COLUMNAS_ASIGNACIONES)


def semaforo(p: pd.DataFrame, hoy: date | None = None) -> pd.DataFrame:
    corte = pd.Timestamp(hoy or date.today())
    activo = p["estado"].isin(ESTADOS_ACTIVOS)
    con_fechas = activo & p["inicio"].notna() & p["fin"].notna()
    duracion = (p["fin"] - p["inicio"]).dt.days.where(lambda d: d > 0)
    esperado = ((corte - p["inicio"]).dt.days / duracion).clip(0, 1).where(con_fechas)
    brecha = (p["avance"] - esperado).where(con_fechas)
    vencido = con_fechas & (p["fin"] < corte) & (p["avance"] < 1)

    sem = p["estado"].astype(object).copy()
    sem[activo & ~con_fechas] = "Sin fecha de cierre"
    sem[con_fechas] = "En tiempo"
    sem[con_fechas & (brecha <= -UMBRAL_MEDIO)] = "Atención media"
    sem[con_fechas & (vencido | (brecha <= -UMBRAL_ALTO))] = "Atención alta"
    return p.assign(
        activo=activo,
        esperado=esperado,
        brecha=brecha,
        dias_restantes=(p["fin"] - corte).dt.days.where(p["fin"].notna()),
        semaforo=sem,
        retrasado=sem == "Atención alta",
    )


def preparar(proyectos: pd.DataFrame, asignaciones: pd.DataFrame, colaboradores: pd.DataFrame) -> dict:
    p = proyectos.reindex(columns=COLUMNAS_PROYECTOS).copy()
    p["avance"] = pd.to_numeric(p["avance"], errors="coerce").fillna(0)
    p["inicio"] = pd.to_datetime(p["inicio"], errors="coerce")
    p["fin"] = pd.to_datetime(p["fin"], errors="coerce")
    p = semaforo(p)

    col = colaboradores.set_index("id")
    a = asignaciones.reindex(columns=COLUMNAS_ASIGNACIONES).copy()
    a["id_empleado"] = a["id_empleado"].where(a["id_empleado"].notna() & (a["id_empleado"] != ""), None)
    a["colaborador"] = a["id_empleado"].map(col["nombre"]).fillna(a["persona"])
    a["area"] = a["id_empleado"].map(col["area"])
    a = a.merge(p[["proyecto_id", "proyecto", "estado", "activo", "semaforo", "avance"]], on="proyecto_id", how="left")

    for rol, columna in [("Desarrollo", "desarrollo"), ("Base de datos", "base_datos"),
                         ("Coordinación", "coordinacion"), ("Command center", "command_center")]:
        nombres = a[a["rol"] == rol].groupby("proyecto_id")["colaborador"].agg(", ".join)
        p[columna] = p["proyecto_id"].map(nombres)

    # Un renglón por proyecto y área de sus responsables (para indicadores por área).
    # La PM dueña del concentrado también cuenta: su área (PMS) tiene todo su portafolio.
    pm = p[["proyecto_id", "portafolio_id"]].rename(columns={"portafolio_id": "id_empleado"})
    areas = pd.concat([a[["proyecto_id", "id_empleado"]], pm]).dropna()
    areas["area"] = areas["id_empleado"].map(col["area"])
    areas = areas.dropna(subset=["area"])[["proyecto_id", "area"]].drop_duplicates()
    pa = p.merge(areas[areas["area"].isin(AREAS)], on="proyecto_id")
    return {"proyectos_todos": p, "asignaciones": a, "proyectos_area": pa}
