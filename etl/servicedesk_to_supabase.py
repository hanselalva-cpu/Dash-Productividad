"""Copia tickets de ServiceDesk (SQL Server) a Supabase.

Uso (desde la raíz del proyecto):
    python -m etl.servicedesk_to_supabase                      # incremental: últimos 60 días + abiertos
    python -m etl.servicedesk_to_supabase --desde 2025-01-01   # carga histórica
    python -m etl.servicedesk_to_supabase --dry-run            # no escribe en Supabase; guarda CSV
    python -m etl.servicedesk_to_supabase --desde 2025-01-01 --area "Seguridad de la información"  # un área

Credenciales en .env: SQLSERVER_HOST, SQLSERVER_DB, SQLSERVER_USER, SQLSERVER_PASSWORD,
SUPABASE_URL, SUPABASE_SECRET_KEY.

Los SPs reciben @Edificio y @Subarea como IDs (los convierten a tinyint) y no aceptan
NULL como "todos", así que se recorre cada edificio × subárea.
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

import pandas as pd
import pyodbc
from dotenv import load_dotenv

from tablero.config import EDIFICIOS, SUBAREAS_POR_AREA

DIAS_VENTANA_INCREMENTAL = 60
LOTE_UPSERT = 500

ESTADOS = {
    "Resuelto": "cerrado",
    "Solucionado": "cerrado",  # trae FechaResuelto y no aparece en RDL_TICKETS_ABIERTOS
    "Cerrado": "cerrado",
    "Cancelar": "cancelado",
    "Cancelado": "cancelado",
}  # cualquier otro estatus (Nuevo Ticket, En Curso, En Espera, Sin Resolver, ...) = abierto

SQL_TICKETS = (
    "SET NOCOUNT ON; EXEC dbo.RDL_TICKETS @FechaInicio=?, @FechaFin=?, @Edificio=?, @Subarea=?"
)
SQL_ABIERTOS = "SET NOCOUNT ON; EXEC dbo.RDL_TICKETS_ABIERTOS @Edificio=?, @Subarea=?"


# =============================================================================
# Extracción
# =============================================================================


def conectar_sql(base: str | None = None) -> pyodbc.Connection:
    return pyodbc.connect(
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={os.environ['SQLSERVER_HOST']};DATABASE={base or os.environ['SQLSERVER_DB']};"
        f"UID={os.environ['SQLSERVER_USER']};PWD={os.environ['SQLSERVER_PASSWORD']};"
        "TrustServerCertificate=yes",
        timeout=15,
    )


def _ejecutar(cn: pyodbc.Connection, sql: str, params: list) -> pd.DataFrame:
    cur = cn.cursor()
    cur.execute(sql, params)
    if cur.description is None:
        return pd.DataFrame()
    columnas = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=columnas)


AREAS_A_CARGAR = dict(SUBAREAS_POR_AREA)  # --area la limita a una sola


def _por_edificio_y_subarea(cn: pyodbc.Connection, sql: str, params_fecha: list) -> pd.DataFrame:
    partes = []
    for area, subareas in AREAS_A_CARGAR.items():
        for subarea_id in subareas:
            for edificio_id in EDIFICIOS:
                df = _ejecutar(cn, sql, [*params_fecha, edificio_id, subarea_id])
                if not df.empty:
                    partes.append(df.assign(area=area, subarea_id=subarea_id, edificio_id=edificio_id))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _meses(desde: date, hasta: date):
    inicio = desde
    while inicio <= hasta:
        siguiente = (inicio.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield inicio, min(siguiente - timedelta(days=1), hasta)
        inicio = siguiente


def _meses_de_cerrados(abiertos_previos: dict[int, date], abiertos: pd.DataFrame, desde: date) -> list[tuple]:
    """Meses (anteriores a la ventana) de tickets que estaban abiertos en Supabase y ya no lo están."""
    ids_abiertos = set(abiertos["TicketId"]) if not abiertos.empty else set()
    meses = {f.replace(day=1) for tid, f in abiertos_previos.items() if tid not in ids_abiertos and f < desde}
    return [(m, min(next(_meses(m, m))[1], desde - timedelta(days=1))) for m in sorted(meses)]


def extraer(cn: pyodbc.Connection, desde: date, hasta: date, abiertos_previos: dict[int, date] | None = None) -> pd.DataFrame:
    abiertos = _por_edificio_y_subarea(cn, SQL_ABIERTOS, [])
    print(f"  RDL_TICKETS_ABIERTOS: {len(abiertos)} filas")
    rangos = _meses_de_cerrados(abiertos_previos or {}, abiertos, desde) + list(_meses(desde, hasta))
    partes = []
    for ini, fin in rangos:
        df = _por_edificio_y_subarea(cn, SQL_TICKETS, [ini, fin])
        print(f"  RDL_TICKETS {ini} -> {fin}: {len(df)} filas")
        partes.append(df)
    # Abiertos al final: su versión gana al deduplicar
    return pd.concat([*partes, abiertos], ignore_index=True)


# =============================================================================
# Transformación
# =============================================================================


def transformar(crudo: pd.DataFrame) -> pd.DataFrame:
    if crudo.empty:
        return crudo
    df = crudo.drop_duplicates("TicketId", keep="last").copy()
    resolutor = df["Resolutor"].fillna("").str.split(" - ", n=1, expand=True).reindex(columns=[0, 1])
    estatus = df["EstatusTicket"].fillna("").str.strip()
    salida = pd.DataFrame(
        {
            "ticket_id": df["TicketId"].astype("int64"),
            "area": df["area"],
            "subarea_id": df["subarea_id"],
            "subarea": df["Subarea"].str.strip(),
            "area_servicedesk": df["Area"].str.strip(),
            "edificio_id": df["edificio_id"],
            "edificio": df["Edificio"].str.strip(),
            "prioridad": df["Prioridad"].str.strip(),
            "categoria": df["Categoria"].str.strip(),
            "estatus": estatus,
            "estado": estatus.map(ESTADOS).fillna("abierto"),
            "fecha_creacion": pd.to_datetime(df["FechaCreacion"]).dt.date,
            "fecha_resuelto": pd.to_datetime(df["FechaResuelto"]),
            "resolutor_id": resolutor[0].str.strip().replace("", None),
            "resolutor": resolutor[1].str.strip().replace("", None),
            "valor": df["Valor"],
        }
    )
    return salida


# =============================================================================
# Carga
# =============================================================================


def cliente_supabase():
    from supabase import create_client

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])


def _a_registros(df: pd.DataFrame) -> list[dict]:
    df = df.copy()
    df["fecha_creacion"] = df["fecha_creacion"].astype(str)
    df["fecha_resuelto"] = df["fecha_resuelto"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["actualizado"] = datetime.now().isoformat(timespec="seconds")
    return df.astype(object).where(df.notna(), None).to_dict("records")


def cargar(sb, df: pd.DataFrame) -> None:
    registros = _a_registros(df)
    for i in range(0, len(registros), LOTE_UPSERT):
        sb.table("tickets").upsert(registros[i : i + LOTE_UPSERT], on_conflict="ticket_id").execute()
    print(f"  Supabase: {len(registros)} tickets insertados/actualizados")


def abiertos_en_supabase(sb) -> dict[int, date]:
    """ticket_id -> fecha_creacion de los tickets que Supabase tiene como abiertos."""
    filas, inicio = [], 0
    while True:
        res = (
            sb.table("tickets").select("ticket_id,fecha_creacion").eq("estado", "abierto")
            .order("ticket_id").range(inicio, inicio + 999).execute()
        )
        filas.extend(res.data)
        if len(res.data) < 1000:
            break
        inicio += 1000
    return {f["ticket_id"]: date.fromisoformat(f["fecha_creacion"]) for f in filas}


def registrar(sb, inicio: datetime, desde: date, hasta: date, filas: int, estado: str, mensaje: str = "") -> None:
    sb.table("etl_ejecuciones").insert(
        {
            "inicio": inicio.isoformat(timespec="seconds"),
            "fin": datetime.now().isoformat(timespec="seconds"),
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "filas": filas,
            "estado": estado,
            "mensaje": mensaje[:1000],
        }
    ).execute()


# =============================================================================
# Main
# =============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", type=date.fromisoformat, help="Fecha inicial (YYYY-MM-DD)")
    parser.add_argument("--hasta", type=date.fromisoformat, default=date.today())
    parser.add_argument("--dry-run", action="store_true", help="No escribe en Supabase; guarda CSV")
    parser.add_argument("--csv", default="tickets_servicedesk.csv", help="Ruta del CSV en --dry-run")
    parser.add_argument("--area", choices=list(SUBAREAS_POR_AREA), help="Cargar solo esta área (ej. histórico de un área nueva)")
    args = parser.parse_args()
    if args.area:
        AREAS_A_CARGAR.clear()
        AREAS_A_CARGAR[args.area] = SUBAREAS_POR_AREA[args.area]

    load_dotenv()
    inicio = datetime.now()
    sb = None if args.dry_run else cliente_supabase()
    desde = args.desde or date.today() - timedelta(days=DIAS_VENTANA_INCREMENTAL)
    print(f"ServiceDesk -> {'CSV' if args.dry_run else 'Supabase'} | {desde} -> {args.hasta}")

    try:
        # Tickets que Supabase tiene abiertos y ya se cerraron fuera de la ventana: se recargan sus meses
        abiertos_previos = abiertos_en_supabase(sb) if sb is not None else {}
        with conectar_sql() as cn:
            tickets = transformar(extraer(cn, desde, args.hasta, abiertos_previos))
        if args.dry_run:
            tickets.to_csv(args.csv, index=False, encoding="utf-8-sig")
            print(f"  {len(tickets)} tickets -> {args.csv}")
        else:
            cargar(sb, tickets)
            registrar(sb, inicio, desde, args.hasta, len(tickets), "ok")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if sb is not None:
            registrar(sb, inicio, desde, args.hasta, 0, "error", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
