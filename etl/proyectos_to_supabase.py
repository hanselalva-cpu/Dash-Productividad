"""Carga los concentrados de proyectos de las PMs (Excel) a Supabase.

Uso (desde la raíz del proyecto):
    python -m etl.proyectos_to_supabase              # reemplaza proyectos y asignaciones en Supabase
    python -m etl.proyectos_to_supabase --dry-run    # solo muestra lo que leyó y los nombres sin homologar

Lee cada .xlsx de PROYECTOS_DIR (por defecto data/proyectos/), hoja "Proyectos": el encabezado es la
fila cuya primera celda dice "Proyecto". La columna "Responsables..." es texto libre del estilo
"Desarrollo: Ana / Luis / BD: Pedro / Aurora Esparza."; los nombres se homologan con
data/alias_personas.csv (alias -> id_empleado; coordinacion=Sí marca a quien coordina).
"""

import argparse
import glob
import os
import re
import sys
import unicodedata
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

from etl.servicedesk_to_supabase import LOTE_UPSERT, cliente_supabase, registrar

RUTA_ALIAS = "data/alias_personas.csv"

ESTADOS = {
    "completo": "Terminado",
    "terminado": "Terminado",
    "en curso": "En desarrollo",
    "atrasado": "En desarrollo",
    "pruebas": "En pruebas",
    "en pruebas": "En pruebas",
    "en espera": "En espera",
    "cancelado": "Cancelado",
}
ROLES = {
    "desarrollo": "Desarrollo",
    "bd": "Base de datos",
    "base de datos": "Base de datos",
    "command center": "Command center",
    "coordinacion": "Coordinación",
}
SIN_PERSONA = {"", "tbd", "por definir", "por asignar", "n/a"}
ETIQUETA = re.compile(r"^\s*(desarrollo|bd|base de datos|command center|coordinaci[oó]n)\s*:\s*(.*)$", re.I)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto).strip(" .").lower()


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar(texto)).strip("-")


def cargar_alias() -> dict[str, tuple[str, bool]]:
    a = pd.read_csv(RUTA_ALIAS, dtype=str).fillna("")
    return {normalizar(r.alias): (r.id_empleado.strip(), r.coordinacion.strip().lower() in ("sí", "si"))
            for r in a.itertuples()}


def homologar(nombre: str, alias: dict) -> tuple[str | None, bool]:
    clave = normalizar(nombre)
    if clave in alias:
        return alias[clave]
    sin_parentesis = normalizar(re.sub(r"\(.*?\)", "", nombre))
    return alias.get(sin_parentesis, (None, False))


def separar_responsables(texto: str, alias: dict) -> list[dict]:
    """'Desarrollo: A / B / BD: C / Aurora.' -> [{persona, id_empleado, rol}, ...]"""
    if not isinstance(texto, str) or not texto.strip():
        return []
    rol, filas = "Desarrollo", []
    for parte in re.split(r"[/\n]", texto):
        m = ETIQUETA.match(parte)
        if m:
            rol = ROLES[normalizar(m.group(1))]
            parte = m.group(2)
        nombre = re.sub(r"\s+", " ", parte).strip(" .")
        if normalizar(nombre) in SIN_PERSONA:
            continue
        id_empleado, coordina = homologar(nombre, alias)
        filas.append({"persona": nombre, "id_empleado": id_empleado,
                      "rol": "Coordinación" if coordina else rol})
    return filas


def leer_archivo(ruta: str, alias: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    crudo = pd.read_excel(ruta, sheet_name="Proyectos", header=None)
    fila_enc = crudo.index[crudo[0].astype(str).str.strip().str.lower() == "proyecto"][0]
    responsable = next((str(v) for v in crudo[0].head(fila_enc) if "responsable del proyecto" in str(v).lower()), "")
    # "Responsable del proyecto: Ana Garate    |    Empresa: ...    |    Actualizado: 04/09/2026"
    portafolio = responsable.split("|")[0].split(":", 1)[-1].strip() or os.path.splitext(os.path.basename(ruta))[0]

    df = crudo.iloc[fila_enc + 1:].copy()
    df.columns = [str(c).strip() for c in crudo.iloc[fila_enc]]
    col_resp = next(c for c in df.columns if c.lower().startswith("responsables"))
    df = df[df["Proyecto"].notna() & (df["Estado"].notna() | df["Progreso"].notna())]

    proyectos, asignaciones = [], []
    for _, r in df.iterrows():
        nombre = str(r["Proyecto"]).strip()
        estado_origen = str(r["Estado"]).strip() if pd.notna(r["Estado"]) else ""
        estado = ESTADOS.get(estado_origen.lower(), "En espera")
        proyecto_id = f"{slug(portafolio)}--{slug(nombre)}"
        avance = pd.to_numeric(r["Progreso"], errors="coerce")
        fecha = lambda c: pd.to_datetime(r.get(c), errors="coerce")  # noqa: E731
        texto = lambda c: str(r[c]).strip() if c in r and pd.notna(r[c]) and str(r[c]).strip() else None  # noqa: E731
        proyectos.append(
            {
                "proyecto_id": proyecto_id,
                "portafolio": portafolio,
                "portafolio_id": homologar(portafolio, alias)[0],
                "proyecto": nombre,
                "objetivo": texto("Objetivo"),
                "estado": estado,
                "estado_origen": estado_origen or None,
                "avance": None if pd.isna(avance) else float(min(max(avance, 0), 1)),
                "inicio": None if pd.isna(fecha("Inicio")) else fecha("Inicio").date().isoformat(),
                "fin": None if pd.isna(fecha("Fin")) else fecha("Fin").date().isoformat(),
                "solicitante": texto("Solicitante"),
                "responsables_texto": texto(col_resp),
                "situacion": texto("Comentarios actuales"),
                "archivo": os.path.basename(ruta),
            }
        )
        vistos = set()
        for a in separar_responsables(r[col_resp], alias):
            clave = (a["persona"], a["rol"])
            if clave not in vistos:
                vistos.add(clave)
                asignaciones.append({"proyecto_id": proyecto_id, **a})
    return pd.DataFrame(proyectos), pd.DataFrame(asignaciones)


def leer_todo(carpeta: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    alias = cargar_alias()
    archivos = [f for f in sorted(glob.glob(os.path.join(carpeta, "*.xlsx"))) if not os.path.basename(f).startswith("~$")]
    if not archivos:
        raise FileNotFoundError(f"No hay archivos .xlsx en {carpeta}")
    partes = [leer_archivo(f, alias) for f in archivos]
    proyectos = pd.concat([p for p, _ in partes], ignore_index=True)
    asignaciones = pd.concat([a for _, a in partes], ignore_index=True)
    duplicados = proyectos[proyectos["proyecto_id"].duplicated()]["proyecto"].tolist()
    if duplicados:
        raise ValueError(f"Proyectos repetidos dentro de un mismo concentrado: {duplicados}")
    for f, (p, a) in zip(archivos, partes):
        print(f"  {os.path.basename(f)}: {len(p)} proyectos, {len(a)} asignaciones")
    return proyectos, asignaciones


def _registros(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(df.notna(), None).to_dict("records")


def cargar(sb, proyectos: pd.DataFrame, asignaciones: pd.DataFrame) -> None:
    ahora = datetime.now().isoformat(timespec="seconds")
    sb.table("proyectos").delete().neq("proyecto_id", "").execute()  # asignaciones se borran en cascada
    regs = _registros(proyectos.assign(actualizado=ahora))
    for i in range(0, len(regs), LOTE_UPSERT):
        sb.table("proyectos").insert(regs[i : i + LOTE_UPSERT]).execute()
    regs = _registros(asignaciones)
    for i in range(0, len(regs), LOTE_UPSERT):
        sb.table("proyecto_asignaciones").insert(regs[i : i + LOTE_UPSERT]).execute()
    print(f"  Supabase: {len(proyectos)} proyectos y {len(asignaciones)} asignaciones")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="No escribe en Supabase")
    args = parser.parse_args()

    load_dotenv()
    carpeta = os.environ.get("PROYECTOS_DIR", "data/proyectos")
    inicio = datetime.now()
    print(f"Proyectos ({carpeta}) -> {'revisión' if args.dry_run else 'Supabase'}")
    sb = None if args.dry_run else cliente_supabase()
    try:
        proyectos, asignaciones = leer_todo(carpeta)
        sin_homologar = sorted(set(asignaciones.loc[asignaciones["id_empleado"].isna(), "persona"]))
        if sin_homologar:
            print(f"  Nombres sin homologar (agregar a {RUTA_ALIAS}): {', '.join(sin_homologar)}")
        if args.dry_run:
            print(proyectos["estado"].value_counts().to_string())
        else:
            cargar(sb, proyectos, asignaciones)
            registrar(sb, inicio, inicio.date(), inicio.date(), len(proyectos), "ok", "[proyectos]")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if sb is not None:
            registrar(sb, inicio, inicio.date(), inicio.date(), 0, "error", f"[proyectos] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
