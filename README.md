# Dashboard de productividad por área

```
SQL Server ServiceDesk ──ETL──▶ Supabase ──▶ Streamlit
(RDL_TICKETS, RDL_TICKETS_ABIERTOS)
```

Áreas: Desarrollo, Eficiencia, Soporte, Base de datos, Gestor de claves, PMS.

## Estado de las fuentes

| Datos | Fuente | Estado |
|---|---|---|
| Tickets | ServiceDesk → Supabase | Listo |
| Personal oficial | `data/personal.csv` → tabla `personal` (`python -m etl.cargar_personal`) | Listo; falta línea de reporte |
| PMS | Fisgón | Pendiente |
| Asistencias, retardos, vacaciones | REPORTES_INCIDENCIAS.dbo.OBTENER_INFORME_EVENTOS → tabla `asistencias` (`python -m etl.asistencias_to_supabase`) | Listo |
| Proyectos | Por definir | Demo |

Mapeo de áreas a subáreas de ServiceDesk, edificios y metas de SLA: `utils/config.py`.

## Instalación

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-etl.txt   # ETL + dashboard (local)
```

`requirements.txt` solo trae lo del dashboard (es lo que instala Streamlit Cloud).
`data/personal.csv` no se sube a git: copiar `data/personal.example.csv` y llenarlo.

## Configuración

1. Supabase > SQL Editor: ejecutar `sql/schema.sql`.
2. `.env` (ETL): credenciales SQL Server + `SUPABASE_URL` / `SUPABASE_SECRET_KEY`.
3. `.streamlit/secrets.toml` (dashboard): copiar de `secrets.toml.example`.

Ninguno de esos archivos se sube a git.

## ETL

```
.venv\Scripts\python -m etl.servicedesk_to_supabase --desde 2025-01-01   # carga histórica (una vez)
.venv\Scripts\python -m etl.servicedesk_to_supabase                      # incremental
.venv\Scripts\python -m etl.servicedesk_to_supabase --dry-run            # solo extrae a CSV
```

- Los SPs reciben `@Edificio` y `@Subarea` como **IDs**; NULL no significa "todos". El ETL recorre edificio × subárea.
- Incremental: últimos 60 días + abiertos actuales + los meses de tickets viejos que estaban abiertos en Supabase y ya se cerraron. Upsert por `ticket_id`.
- Cada corrida queda en la tabla `etl_ejecuciones`; el dashboard muestra la última.
- Programado diario 10:00 en el Programador de tareas de Windows: tarea "Dash Productividad - ETL ServiceDesk" -> `run_etl.bat` (log en `logs/etl.log`). Requiere esta PC encendida y en red.

## Dashboard

```
.venv\Scripts\streamlit run streamlit_app.py
```

Sin `secrets.toml` los tickets salen en modo demo.

## Reglas de cálculo

- **Estado**: `Resuelto`/`Solucionado` = cerrado, `Cancelar` = cancelado, el resto = abierto.
- **Resolución (días)**: `FechaResuelto − FechaCreacion`. ServiceDesk no trae la hora de creación, así que se cuenta desde las 00:00.
- **SLA**: resolución ≤ meta por prioridad (`SLA_DIAS`: Alta 1, Media 2, Baja 3 días).
- **Personas**: listado oficial (`data/personal.csv`). Los tickets cuentan en el área de su subárea de ServiceDesk; los indicadores por persona usan `resolutor_id` = `id_empleado`. Estrategia digital y Seguridad de la información quedan fuera de las 6 áreas.
- **Backlog**: tickets abiertos hoy, sin importar el periodo.
- **Retardo**: entrada > `InicioJornada` + 15 min (el SP marca R desde el primer minuto; se recalcula).
- **% Asistencia**: días laborados (A/R/TC) ÷ días laborables (sin descansos, vacaciones ni incapacidades).
- **Validación de checadas**: días laborados sin entrada, sin salida, sin horario o con una sola checada.

## Publicación (Streamlit Community Cloud)

1. https://share.streamlit.io → **Create app** → repo `Dash-Productividad`, rama `main`, archivo `streamlit_app.py`.
2. **Advanced settings → Secrets**: pegar el contenido de `.streamlit/secrets.toml`.
3. **Share**: el repo es privado, así que la app solo la ven los correos invitados.
4. **Accesos**: en Secrets, sección `[accesos]`, cada correo invitado -> su `id_empleado`.
   Quien no tiene jefe en el organigrama ve todo; los demás ven solo su equipo hacia abajo
   (ver `utils/acceso.py`). Un correo invitado que no esté en `[accesos]` ve "Sin acceso".

El ETL no corre en la nube (SQL Server está en la red interna): sigue en la tarea programada de esta PC
y el dashboard publicado lee de Supabase.
