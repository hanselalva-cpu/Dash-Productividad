"""Carga data/personal.csv a la tabla `personal` de Supabase (upsert por id_empleado).

Uso: python -m etl.cargar_personal
"""

import sys
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from etl.servicedesk_to_supabase import cliente_supabase

RUTA = "data/personal.csv"


def main() -> int:
    load_dotenv()
    p = pd.read_csv(RUTA, dtype=str).fillna("")
    p["incluir"] = p["incluir"].str.strip().str.lower().isin(["sí", "si", "true", "1"])
    p["reporta_a"] = p["reporta_a"].str.strip().replace("", None)
    p["actualizado"] = datetime.now().isoformat(timespec="seconds")
    sb = cliente_supabase()
    registros = p.astype(object).where(p.notna(), None).to_dict("records")
    # Primero sin reporta_a para que la FK no falle si el jefe aún no existe; luego con reporta_a
    sb.table("personal").upsert([{**r, "reporta_a": None} for r in registros], on_conflict="id_empleado").execute()
    sb.table("personal").upsert(registros, on_conflict="id_empleado").execute()
    print(f"personal: {len(registros)} registros cargados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
