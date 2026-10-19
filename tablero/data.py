"""Carga de datos para el dashboard y filtros.

- Tickets: tabla `tickets` de Supabase (copia de ServiceDesk, ver etl/). Sin credenciales: demo.
- Asistencias y vacaciones: tabla `asistencias` (copia de REPORTES_INCIDENCIAS). Sin datos: demo.
- Personal: tabla `personal` o data/personal.csv.
- Proyectos: aún sin fuente (demo).
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from tablero.config import (
    AREAS, AREAS_SIN_FUENTE, EDIFICIOS, ESTATUS_LABORABLE, SLA_DIAS, SLA_DIAS_DEFAULT, SUBAREAS_POR_AREA,
    TOLERANCIA_RETARDO_MIN,
)

EDIFICIOS_LISTA = list(EDIFICIOS.values())

COLUMNAS_TICKETS = [
    "ticket_id", "area", "subarea_id", "subarea", "area_servicedesk", "edificio_id", "edificio", "prioridad",
    "categoria", "estatus", "estado", "fecha_creacion", "fecha_resuelto", "resolutor_id", "resolutor", "valor",
]
COLUMNAS_ASISTENCIAS = [
    "id_empleado", "fecha", "incidencia", "descripcion", "estatus", "inicio_jornada", "entrada", "salida",
    "minutos_tarde", "retardo", "sin_entrada", "sin_salida", "sin_horario", "comentario",
]


# =============================================================================
# Supabase
# =============================================================================


def supabase_configurado() -> bool:
    try:
        return "supabase" in st.secrets
    except Exception:
        return False


@st.cache_resource
def _cliente():
    from supabase import create_client

    cfg = st.secrets["supabase"]
    return create_client(cfg["url"], cfg["key"])


def _leer_tabla(tabla: str, columnas: list[str], orden: list[str] | None = None, lote: int = 1000) -> pd.DataFrame:
    """Lee la tabla completa paginando (Supabase devuelve máx. 1000 filas por consulta).

    `orden` debe ser único por fila para que la paginación no repita ni salte filas.
    """
    filas, inicio = [], 0
    while True:
        consulta = _cliente().table(tabla).select(",".join(columnas))
        for c in orden or columnas[:1]:
            consulta = consulta.order(c)
        res = consulta.range(inicio, inicio + lote - 1).execute()
        filas.extend(res.data)
        if len(res.data) < lote:
            break
        inicio += lote
    return pd.DataFrame(filas, columns=columnas)


def _ultima_ejecucion_etl() -> dict | None:
    res = (
        _cliente().table("etl_ejecuciones").select("fin,estado,filas,mensaje")
        .order("id", desc=True).limit(1).execute()
    )
    return res.data[0] if res.data else None


@st.cache_data(ttl="10m", show_spinner="Cargando datos...")
def cargar_datos() -> dict:
    rng = np.random.default_rng(7)
    if supabase_configurado():
        tickets = _leer_tabla("tickets", COLUMNAS_TICKETS)
        fuentes = {"tickets": "Supabase (ServiceDesk)"}
        etl = _ultima_ejecucion_etl()
    else:
        tickets = _demo_tickets(rng)
        fuentes = {"tickets": "Demo"}
        etl = None

    t = _preparar_tickets(tickets)
    colaboradores, fuente_personal = _colaboradores(t, rng)

    asistencias, fuente_asistencia = None, "Demo"
    if supabase_configurado():
        try:
            asistencias = _leer_tabla("asistencias", COLUMNAS_ASISTENCIAS, orden=["id_empleado", "fecha"])
            fuente_asistencia = "Supabase (Incidencias)"
        except Exception:
            asistencias = None
    if asistencias is None or asistencias.empty:
        asistencias, fuente_asistencia = _demo_asistencia(colaboradores, rng), "Demo"

    d = {
        "tickets": t,
        "colaboradores": colaboradores,
        "proyectos": _preparar_proyectos(_demo_proyectos(colaboradores, rng)),
        **_preparar_asistencia(colaboradores, asistencias),
        "fuentes": {**fuentes, "personal": fuente_personal, "asistencia": fuente_asistencia, "proyectos": "Demo"},
        "etl": etl,
    }
    return d


# =============================================================================
# Preparación
# =============================================================================


def _preparar_tickets(crudo: pd.DataFrame) -> pd.DataFrame:
    t = crudo.reindex(columns=COLUMNAS_TICKETS).copy()
    t["fecha_creacion"] = pd.to_datetime(t["fecha_creacion"], errors="coerce")
    t["fecha_resuelto"] = pd.to_datetime(t["fecha_resuelto"], errors="coerce")
    t["edificio"] = t["edificio"].astype("string").str.strip()
    t["colaborador_id"] = t["resolutor_id"]
    t["colaborador"] = t["resolutor"]
    t["dias_resolucion"] = ((t["fecha_resuelto"] - t["fecha_creacion"]).dt.total_seconds() / 86400).where(
        t["estado"] == "cerrado"
    )
    t["sla_dias"] = t["prioridad"].map(SLA_DIAS).fillna(SLA_DIAS_DEFAULT)
    t["cumple_sla"] = (t["dias_resolucion"] <= t["sla_dias"]).where(t["estado"] == "cerrado")
    t["semana"] = t["fecha_creacion"].dt.to_period("W").dt.start_time
    return t


RUTA_PERSONAL = "data/personal.csv"


def _leer_personal() -> tuple[pd.DataFrame | None, str]:
    """Listado oficial de personal: tabla `personal` de Supabase o, si no existe, data/personal.csv."""
    if supabase_configurado():
        try:
            p = _leer_tabla("personal", ["id_empleado", "nombre", "grupo", "area", "reporta_a", "incluir"])
            if not p.empty:
                return p, "Supabase"
        except Exception:
            pass
    try:
        p = pd.read_csv(RUTA_PERSONAL, dtype=str).fillna({"reporta_a": ""})
        p["incluir"] = p["incluir"].str.strip().str.lower().isin(["sí", "si", "true", "1"])
        return p, "data/personal.csv"
    except FileNotFoundError:
        return None, "Resolutores de ServiceDesk"


def _colaboradores(t: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, str]:
    personal, fuente = _leer_personal()
    if personal is None:
        return _colaboradores_desde_tickets(t, rng), fuente
    p = personal[personal["incluir"].astype(bool)]
    nombres = p.set_index("id_empleado")["nombre"].str.title()
    col = pd.DataFrame(
        {
            "id": p["id_empleado"].str.strip(),
            "nombre": p["nombre"].str.title(),
            "puesto": p["grupo"].str.capitalize(),
            "area": p["area"],
            "reporta_a": p["reporta_a"].replace("", None).map(nombres),
            "reporta_a_id": p["reporta_a"].replace("", None),
        }
    ).sort_values(["area", "nombre"]).reset_index(drop=True)
    return col, fuente


def _colaboradores_desde_tickets(t: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Respaldo sin listado oficial: personas = resolutores; su área es donde resolvieron más tickets."""
    # Excluye "SOLICITANTE": tickets cancelados por el propio usuario, no es una persona del equipo
    con_resolutor = t[t["resolutor_id"].fillna("").str.match(r"^[A-Z]\d+$")]
    if con_resolutor.empty:
        return pd.DataFrame(columns=["id", "nombre", "puesto", "area", "reporta_a", "reporta_a_id"])
    area = con_resolutor.groupby("resolutor_id")["area"].agg(lambda s: s.value_counts().index[0])
    nombre = con_resolutor.groupby("resolutor_id")["resolutor"].last()
    col = pd.DataFrame({"nombre": nombre, "area": area}).rename_axis("id").reset_index().sort_values("id")
    col["puesto"] = None
    col["reporta_a"] = None
    col["reporta_a_id"] = None
    return col.reset_index(drop=True)


def _preparar_proyectos(p: pd.DataFrame) -> pd.DataFrame:
    for c in ["fecha_inicio", "fecha_fin_plan", "fecha_fin_real"]:
        p[c] = pd.to_datetime(p[c], errors="coerce")
    hoy = pd.Timestamp(date.today())
    completado = p["estado"] == "completado"
    p["retrasado"] = (
        (completado & (p["fecha_fin_real"] > p["fecha_fin_plan"]))
        | (~completado & (hoy > p["fecha_fin_plan"]))
        | ((p["estado"] == "en_curso") & (p["avance_real"] < p["avance_plan"] - 10))
        | (p["estado"] == "detenido")
    )
    return p


def _preparar_asistencia(col: pd.DataFrame, crudo: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Una fila por persona y día. El retardo ya viene calculado (entrada > inicio de jornada + tolerancia)."""
    col_idx = col.set_index("id")
    a = crudo.reindex(columns=COLUMNAS_ASISTENCIAS).copy()
    a["colaborador_id"] = a["id_empleado"]
    a["fecha"] = pd.to_datetime(a["fecha"], errors="coerce")
    a["area"] = a["colaborador_id"].map(col_idx["area"])
    a["colaborador"] = a["colaborador_id"].map(col_idx["nombre"])
    for c in ["retardo", "sin_entrada", "sin_salida", "sin_horario"]:
        a[c] = a[c].fillna(False).astype(bool)
    a["minutos_tarde"] = pd.to_numeric(a["minutos_tarde"], errors="coerce")
    a["presente"] = a["estatus"].isin(["asistencia", "retardo"])
    a["laborable"] = a["estatus"].isin(ESTATUS_LABORABLE)
    a["minutos_retardo"] = a["minutos_tarde"].where(a["retardo"])
    # Entrada y salida casi iguales: solo checó una vez (el retardo puede ser falso)
    duracion = (pd.to_timedelta(a["salida"].astype("string"), errors="coerce")
                - pd.to_timedelta(a["entrada"].astype("string"), errors="coerce")).dt.total_seconds() / 60
    a["una_checada"] = a["presente"] & duracion.between(-10, 10)
    a["semana"] = a["fecha"].dt.to_period("W").dt.start_time
    return {"asistencias": a, "vacaciones": _bloques_vacaciones(a)}


def _bloques_vacaciones(a: pd.DataFrame) -> pd.DataFrame:
    """Agrupa días de vacaciones consecutivos (huecos de hasta 3 días, ej. fin de semana) en periodos."""
    vac = a[a["estatus"] == "vacaciones"].sort_values(["colaborador_id", "fecha"])
    if vac.empty:
        return pd.DataFrame(columns=["colaborador_id", "colaborador", "area", "fecha_inicio", "fecha_fin", "dias"])
    nuevo = (vac["colaborador_id"] != vac["colaborador_id"].shift()) | (vac["fecha"].diff().dt.days > 3)
    vac = vac.assign(bloque=nuevo.cumsum())
    return (
        vac.groupby("bloque")
        .agg(colaborador_id=("colaborador_id", "first"), colaborador=("colaborador", "first"), area=("area", "first"),
             fecha_inicio=("fecha", "min"), fecha_fin=("fecha", "max"), dias=("fecha", "size"))
        .reset_index(drop=True)
    )


# =============================================================================
# Filtros
# =============================================================================


def periodo_anterior(inicio: date, fin: date) -> tuple[date, date]:
    dias = (fin - inicio).days + 1
    return inicio - timedelta(days=dias), inicio - timedelta(days=1)


def filtrar(d: dict, inicio: date, fin: date, areas: list[str], edificios: list[str] | None = None) -> dict:
    ini, fin_ts = pd.Timestamp(inicio), pd.Timestamp(fin) + pd.Timedelta(days=1)
    en_area = lambda df: df[df["area"].isin(areas)]  # noqa: E731

    t = en_area(d["tickets"])
    if edificios is not None:
        t = t[t["edificio"].isin(edificios)]
    p = en_area(d["proyectos"])
    a = en_area(d["asistencias"])
    v = en_area(d["vacaciones"])

    return {
        "colaboradores": en_area(d["colaboradores"]),
        "tickets": t[(t["fecha_creacion"] >= ini) & (t["fecha_creacion"] < fin_ts)],
        "backlog": t[t["estado"] == "abierto"],
        "proyectos": p[(p["fecha_inicio"] < fin_ts) & (p["fecha_fin_plan"].fillna(p["fecha_inicio"]) >= ini)],
        "asistencias": a[(a["fecha"] >= ini) & (a["fecha"] < fin_ts)],
        "vacaciones": v[(v["fecha_inicio"] < fin_ts) & (v["fecha_fin"] >= ini)],
    }


# =============================================================================
# Datos demo
# =============================================================================

_NOMBRES = [
    "Ana", "Luis", "María", "Carlos", "Sofía", "Jorge", "Valeria", "Miguel", "Fernanda", "Ricardo",
    "Daniela", "Alejandro", "Paola", "Roberto", "Gabriela", "Eduardo", "Lucía", "Andrés", "Mariana", "Héctor",
]
_APELLIDOS = [
    "García", "Hernández", "López", "Martínez", "González", "Pérez", "Rodríguez", "Sánchez",
    "Ramírez", "Torres", "Flores", "Rivera", "Gómez", "Díaz", "Cruz", "Morales", "Ortiz", "Reyes",
]
# (personas, tickets por día hábil, % incidentes) — aproximado a lo observado en ServiceDesk
_PERFIL = {
    "Desarrollo": (6, 4, 0.15),
    "Eficiencia": (5, 3, 0.2),
    "Soporte": (11, 37, 0.15),
    "Base de datos": (5, 3.5, 0.2),
    "Gestor de claves": (3, 22, 0.1),
}
_ABIERTOS = ["En Curso", "Nuevo Ticket", "Sin Resolver", "En Espera"]


def _demo_tickets(rng: np.random.Generator) -> pd.DataFrame:
    hoy = pd.Timestamp(date.today())
    filas = []
    for area, (n, tasa, pct_inc) in _PERFIL.items():
        personas = [
            (f"E0{rng.integers(10000, 29999)}", f"{rng.choice(_NOMBRES)} {rng.choice(_APELLIDOS)}") for _ in range(n)
        ]
        peso = rng.uniform(0.5, 1.5, n)
        lentitud = rng.uniform(0.7, 1.3)
        subareas = SUBAREAS_POR_AREA[area]
        for dia in pd.bdate_range(hoy - pd.Timedelta(days=200), hoy):
            for _ in range(rng.poisson(tasa)):
                prioridad = rng.choice(["Alta", "Media", "Baja"], p=[0.36, 0.22, 0.42])
                dias = SLA_DIAS[prioridad] * lentitud * rng.lognormal(-0.6, 0.9)
                resuelto = dia + pd.Timedelta(days=float(dias))
                r = rng.random()
                if resuelto > pd.Timestamp.now():
                    estatus = rng.choice(_ABIERTOS)
                else:
                    estatus = "Cancelar" if r < 0.08 else "Resuelto"
                pid, pnombre = personas[rng.choice(n, p=peso / peso.sum())]
                edificio_id = int(rng.choice(list(EDIFICIOS), p=[0.5, 0.04, 0.2, 0.01, 0.25]))
                filas.append(
                    {
                        "ticket_id": len(filas) + 100000,
                        "area": area,
                        "subarea_id": int(rng.choice(subareas)),
                        "edificio_id": edificio_id,
                        "edificio": EDIFICIOS[edificio_id],
                        "prioridad": prioridad,
                        "categoria": "Incidente" if r < pct_inc else rng.choice(["Requerimiento", "Sin Categoria"], p=[0.9, 0.1]),
                        "estatus": estatus,
                        "estado": {"Resuelto": "cerrado", "Cancelar": "cancelado"}.get(estatus, "abierto"),
                        "fecha_creacion": dia,
                        "fecha_resuelto": resuelto if estatus == "Resuelto" else None,
                        "resolutor_id": pid if estatus != "Nuevo Ticket" else None,
                        "resolutor": pnombre if estatus != "Nuevo Ticket" else None,
                        "valor": 1,
                    }
                )
    return pd.DataFrame(filas)


def _demo_proyectos(col: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    hoy = date.today()
    filas = []
    for area in [a for a in AREAS if a not in AREAS_SIN_FUENTE]:
        miembros = col.loc[col["area"] == area, "nombre"].to_numpy()
        for n in range(int(rng.integers(3, 6))):
            inicio = hoy - timedelta(days=int(rng.integers(20, 180)))
            fin_plan = inicio + timedelta(days=int(rng.integers(45, 150)))
            avance_plan = float(np.clip((hoy - inicio).days / (fin_plan - inicio).days * 100, 0, 100))
            avance_real = float(np.clip(avance_plan + rng.normal(-5, 15), 0, 100))
            completado = avance_real >= 100 or (hoy > fin_plan and rng.random() < 0.6)
            filas.append(
                {
                    "area": area,
                    "responsable": rng.choice(miembros) if len(miembros) else None,
                    "nombre": f"Proyecto {area} {n + 1}",
                    "fecha_inicio": inicio,
                    "fecha_fin_plan": fin_plan,
                    "fecha_fin_real": fin_plan + timedelta(days=int(rng.integers(-10, 20))) if completado else None,
                    "avance_plan": round(avance_plan),
                    "avance_real": 100 if completado else round(avance_real),
                    "estado": "completado" if completado else rng.choice(["en_curso", "en_curso", "en_curso", "detenido"]),
                }
            )
    return pd.DataFrame(filas)


def _demo_asistencia(col: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Mismo formato que la tabla `asistencias` de Supabase."""
    hoy = date.today()
    filas = []
    for cid in col["id"]:
        inicio_jornada = rng.choice([8, 9])
        prob_retardo = rng.uniform(0.02, 0.2)
        vacaciones = set()
        for _ in range(int(rng.integers(1, 3))):
            arranque = pd.Timestamp(hoy) - pd.Timedelta(days=int(rng.integers(0, 200)))
            vacaciones.update(pd.bdate_range(arranque, periods=int(rng.integers(1, 6))))
        for dia in pd.bdate_range(hoy - timedelta(days=200), hoy):
            r = rng.random()
            estatus = ("vacaciones" if dia in vacaciones else "falta" if r < 0.02
                       else "incapacidad" if r < 0.03 else "asistencia")
            fila = {"id_empleado": cid, "fecha": dia, "estatus": estatus, "retardo": False}
            if estatus == "asistencia":
                tarde = int(rng.integers(16, 60)) if rng.random() < prob_retardo else int(rng.integers(-20, 15))
                fila.update(
                    inicio_jornada=f"{inicio_jornada:02d}:00:00",
                    minutos_tarde=tarde,
                    retardo=tarde > TOLERANCIA_RETARDO_MIN,
                    sin_salida=bool(rng.random() < 0.05),
                )
                fila["estatus"] = "retardo" if fila["retardo"] else "asistencia"
            filas.append(fila)
    return pd.DataFrame(filas)


# =============================================================================
# Acceso
# =============================================================================


def datos_visibles() -> dict:
    """Datos recortados a lo que puede ver el usuario actual (ver tablero/acceso.py). Usar en todas las páginas."""
    from tablero.acceso import restringir

    acceso = st.session_state.get("acceso")
    if not acceso:
        st.stop()  # sin acceso resuelto no se muestra nada
    return restringir(cargar_datos(), acceso["personas"], acceso["areas"])
