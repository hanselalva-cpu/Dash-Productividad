# Dashboard de productividad por área

```
SQL Server ServiceDesk ──ETL──▶ Supabase ──▶ Streamlit
(RDL_TICKETS, RDL_TICKETS_ABIERTOS)
```

Áreas: Desarrollo, Eficiencia, Soporte, Base de datos, Gestor de claves, PMS, Seguridad de la información.

## Estado de las fuentes

| Datos | Fuente | Estado |
|---|---|---|
| Tickets | ServiceDesk → Supabase | Listo |
| Personal oficial | `data/personal.csv` → tabla `personal` (`python -m etl.cargar_personal`) | Listo; falta línea de reporte |
| PMS | Fisgón | Pendiente |
| Asistencias, retardos, vacaciones | REPORTES_INCIDENCIAS.dbo.OBTENER_INFORME_EVENTOS → tabla `asistencias` (`python -m etl.asistencias_to_supabase`) | Listo |
| Proyectos | Concentrados Excel de las PMs (`data/proyectos/`) → tablas `proyectos` y `proyecto_asignaciones` (`python -m etl.proyectos_to_supabase`) | Listo |

Mapeo de áreas a subáreas de ServiceDesk, edificios y metas de SLA: `tablero/config.py`.

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
.venv\Scripts\python -m etl.servicedesk_to_supabase --desde 2025-01-01 --area "Seguridad de la información"  # histórico de un área
```

- Los SPs reciben `@Edificio` y `@Subarea` como **IDs**; NULL no significa "todos". El ETL recorre edificio × subárea.
- Incremental: últimos 60 días + abiertos actuales + los meses de tickets viejos que estaban abiertos en Supabase y ya se cerraron. Upsert por `ticket_id`.
- Cada corrida queda en la tabla `etl_ejecuciones`; el dashboard muestra la última.
- Programado diario 10:00, 12:00, 16:00 y 18:00 en el Programador de tareas de Windows: tarea "Dash Productividad - ETL ServiceDesk" -> `run_etl.bat` (log en `logs/etl.log`). Requiere esta PC encendida y en red.

## Dashboard

```
.venv\Scripts\streamlit run streamlit_app.py
```

Sin `secrets.toml` los tickets salen en modo demo.

## Reglas de cálculo

- **Estado**: `Resuelto`/`Solucionado` = cerrado, `Cancelar` = cancelado, el resto = abierto.
- **Resolución (días)**: `FechaResuelto − FechaCreacion`. ServiceDesk no trae la hora de creación, así que se cuenta desde las 00:00.
- **SLA**: resolución ≤ meta por prioridad (`SLA_DIAS`: Alta 1, Media 2, Baja 3 días).
- **Personas**: listado oficial (`data/personal.csv`). Los tickets cuentan en el área de su subárea de ServiceDesk; los indicadores por persona usan `resolutor_id` = `id_empleado`. Estrategia digital y Dirección quedan fuera de las áreas: no entran en indicadores, solo en el calendario de vacaciones (cada usuario ve ahí a su equipo, su jefe y quienes reportan al mismo jefe).
- **Backlog**: tickets abiertos hoy, sin importar el periodo.
- **Retardo**: entrada > `InicioJornada` + 15 min (el SP marca R desde el primer minuto; se recalcula).
- **Vacaciones programadas**: el ETL de asistencias consulta hasta 2 meses adelante; los días futuros se borran y recargan en cada corrida (una cancelación desaparece). En el calendario se ven con borde punteado.
- **% Asistencia**: días laborados (A/R/TC) ÷ días laborables (sin descansos, vacaciones ni incapacidades).
- **Proyectos**: semáforo = avance contra avance esperado (días transcurridos ÷ días planeados). Atención alta: vencido o 30 pts+ abajo; media: 15–30 pts. Responsables homologados con `data/alias_personas.csv` (no se sube a git). El área de un proyecto son las áreas de sus responsables; PMS cuenta todo su portafolio.
- **Validación de checadas**: días laborados sin entrada, sin salida, sin horario o con una sola checada.

## Publicación (Streamlit Community Cloud)

1. https://share.streamlit.io → **Create app** → repo `Dash-Productividad`, rama `main`, archivo `streamlit_app.py`.
2. **Advanced settings → Secrets**: pegar el contenido de `.streamlit/secrets.toml`.
3. **Share**: el repo es privado, así que la app solo la ven los correos invitados.
4. **Accesos**: en Secrets, sección `[accesos]`, cada correo invitado -> su `id_empleado`.
   Quien no tiene jefe en el organigrama ve todo; los demás ven solo su equipo hacia abajo
   (ver `tablero/acceso.py`). Un correo invitado que no esté en `[accesos]` ve "Sin acceso".
5. **Contraseñas**: Community Cloud no pasa el correo del visitante, así que la app pide correo y contraseña.
   `python -m tools.crear_usuario` genera la línea para la sección `[usuarios]` de Secrets (hash, no texto).

El ETL no corre en la nube (SQL Server está en la red interna): sigue en la tarea programada de esta PC
y el dashboard publicado lee de Supabase.
