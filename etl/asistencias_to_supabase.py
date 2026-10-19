"""Copia asistencias de REPORTES_INCIDENCIAS (SQL Server) a Supabase, solo del personal del listado.

Uso (desde la raíz del proyecto):
    python -m etl.asistencias_to_supabase                      # incremental: últimos 45 días
    python -m etl.asistencias_to_supabase --desde 2025-01-01   # carga histórica
    python -m etl.asistencias_to_supabase --dry-run            # no escribe en Supabase; guarda CSV

Valida cada día de cada persona: el retardo se recalcula como entrada > InicioJornada + 15 min
(el SP marca R desde el primer minuto) y se marcan días laborados sin checada o sin horario.
"""

import argparse
import sys
from datetime import date, datetime, timedelta

import pandas as pd
from dotenv import load_dotenv

from etl.servicedesk_to_supabase import LOTE_UPSERT, _ejecutar, _meses, cliente_supabase, conectar_sql
from tablero.config import ESTATUS_INCIDENCIA, TOLERANCIA_RETARDO_MIN

BASE = "REPORTES_INCIDENCIAS"
SQL = "SET NOCOUNT ON; EXEC dbo.OBTENER_INFORME_EVENTOS @FECHA_INICIO=?, @FECHA_FIN=?"
DIAS_VENTANA_INCREMENTAL = 45  # las incidencias se justifican/corrigen después del día
RUTA_PERSONAL = "data/personal.csv"


def extraer(desde: date, hasta: date, ids: set[str]) -> pd.DataFrame:
    partes = []
    with conectar_sql(BASE) as cn:
        for ini, fin in _meses(desde, hasta):
            df = _ejecutar(cn, SQL, [ini, fin])
            df = df[df["Personal"].isin(ids)] if not df.empty else df
            print(f"  OBTENER_INFORME_EVENTOS {ini} -> {fin}: {len(df)} filas del personal")
            partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def _minutos(serie: pd.Series) -> pd.Series:
    return pd.to_timedelta(serie.astype("string"), errors="coerce").dt.total_seconds() / 60


def _hora(serie: pd.Series) -> pd.Series:
    """time -> 'HH:MM:SS'; 00:00:00 = sin checada -> None."""
    texto = serie.astype("string").str.slice(0, 8)
    return texto.where(texto.notna() & (texto != "00:00:00"), None)


def transformar(crudo: pd.DataFrame) -> pd.DataFrame:
    if crudo.empty:
        return crudo
    df = crudo.drop_duplicates(["Personal", "Fecha"], keep="last").copy()
    incidencia = df["Incidencia"].fillna("").str.strip()
    estatus = incidencia.map(ESTATUS_INCIDENCIA).fillna("sin_registro")
    entrada, salida = _hora(df["HoraEntradaChecador"]), _hora(df["HoraSalidaChecador"])
    minutos_tarde = (_minutos(entrada) - _minutos(df["InicioJornada"])).round(1)
    laborado = estatus == "asistencia"
    retardo = laborado & (minutos_tarde > TOLERANCIA_RETARDO_MIN)
    texto = lambda c: df[c].fillna("").astype("string").str.strip().replace("", None)  # noqa: E731
    return pd.DataFrame(
        {
            "id_empleado": df["Personal"].str.strip(),
            "fecha": pd.to_datetime(df["Fecha"]).dt.date.astype(str),
            "incidencia": incidencia.replace("", None),
            "descripcion": texto("Descripcion"),
            "estatus": estatus.where(~retardo, "retardo"),
            "inicio_jornada": _hora(df["InicioJornada"]),
            "fin_jornada": _hora(df["FinJornada"]),
            "entrada": entrada,
            "salida": salida,
            "minutos_tarde": minutos_tarde.where(laborado),
            "retardo": retardo,
            "sin_entrada": laborado & entrada.isna(),
            "sin_salida": laborado & salida.isna(),
            "sin_horario": laborado & df["InicioJornada"].isna(),
            "campana": texto("Campana"),
            "puesto": texto("Puesto"),
            "reporta_a": texto("ReportaA"),
            "edificio": texto("Edificio"),
            "comentario": texto("ComentarioIncidencia"),
        }
    )


def cargar(sb, df: pd.DataFrame) -> None:
    df = df.assign(actualizado=datetime.now().isoformat(timespec="seconds"))
    registros = df.astype(object).where(df.notna(), None).to_dict("records")
    for i in range(0, len(registros), LOTE_UPSERT):
        sb.table("asistencias").upsert(registros[i : i + LOTE_UPSERT], on_conflict="id_empleado,fecha").execute()
    print(f"  Supabase: {len(registros)} días insertados/actualizados")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", type=date.fromisoformat, help="Fecha inicial (YYYY-MM-DD)")
    parser.add_argument("--hasta", type=date.fromisoformat, default=date.today())
    parser.add_argument("--dry-run", action="store_true", help="No escribe en Supabase; guarda CSV")
    parser.add_argument("--csv", default="asistencias.csv", help="Ruta del CSV en --dry-run")
    args = parser.parse_args()

    load_dotenv()
    inicio = datetime.now()
    desde = args.desde or date.today() - timedelta(days=DIAS_VENTANA_INCREMENTAL)
    ids = set(pd.read_csv(RUTA_PERSONAL, dtype=str)["id_empleado"].str.strip())
    print(f"REPORTES_INCIDENCIAS -> {'CSV' if args.dry_run else 'Supabase'} | {desde} -> {args.hasta} | {len(ids)} personas")

    sb = None if args.dry_run else cliente_supabase()
    try:
        asistencias = transformar(extraer(desde, args.hasta, ids))
        if args.dry_run:
            asistencias.to_csv(args.csv, index=False, encoding="utf-8-sig")
            print(f"  {len(asistencias)} días -> {args.csv}")
        else:
            cargar(sb, asistencias)
            _registrar(sb, inicio, desde, args.hasta, len(asistencias), "ok")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if sb is not None:
            _registrar(sb, inicio, desde, args.hasta, 0, "error", str(e))
        return 1
    return 0


def _registrar(sb, inicio, desde, hasta, filas, estado, mensaje=""):
    from etl.servicedesk_to_supabase import registrar

    registrar(sb, inicio, desde, hasta, filas, estado, f"[asistencias] {mensaje}".strip())


if __name__ == "__main__":
    sys.exit(main())
