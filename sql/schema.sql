-- Esquema Supabase para el dashboard de productividad por área.
-- Ejecutar en Supabase > SQL Editor.
--
-- tickets: copia de ServiceDesk (SQL Server 10.52.108.79) vía etl/servicedesk_to_supabase.py
--          a partir de dbo.RDL_TICKETS y dbo.RDL_TICKETS_ABIERTOS.
-- Pendientes: asistencias/retardos/vacaciones (SP por definir) y PMS (Fisgón).

create table if not exists tickets (
    ticket_id         bigint primary key,           -- TicketId de ServiceDesk
    area              text not null,                -- área del dashboard (utils/config.py)
    subarea_id        smallint not null,
    subarea           text,
    area_servicedesk  text,                         -- Area tal como viene de ServiceDesk
    edificio_id       smallint not null,
    edificio          text,
    prioridad         text,                         -- Alta / Media / Baja
    categoria         text,                         -- Requerimiento / Incidente / Sin Categoria
    estatus           text,                         -- EstatusTicket original
    estado            text not null
                      check (estado in ('abierto', 'cerrado', 'cancelado')),
    fecha_creacion    date not null,
    fecha_resuelto    timestamp,                    -- hora local de ServiceDesk
    resolutor_id      text,                         -- número de empleado (ej. E012345)
    resolutor         text,
    valor             int,
    actualizado       timestamp not null default now()
);

create index if not exists idx_tickets_area_fecha on tickets (area, fecha_creacion);
create index if not exists idx_tickets_estado     on tickets (estado);

create table if not exists etl_ejecuciones (
    id       bigserial primary key,
    inicio   timestamp not null,
    fin      timestamp not null,
    desde    date,
    hasta    date,
    filas    int,
    estado   text not null check (estado in ('ok', 'error')),
    mensaje  text
);

-- RLS activo y sin políticas para anon: los datos no quedan públicos.
-- ETL y dashboard usan la service_role key (solo en servidor: .env / .streamlit/secrets.toml).
alter table tickets          enable row level security;
alter table etl_ejecuciones  enable row level security;

-- Personal oficial (fuente: data/personal.csv, cargado con etl/cargar_personal.py)
create table if not exists personal (
    id_empleado  text primary key,                 -- mismo formato que resolutor_id (ej. E012345)
    nombre       text not null,
    grupo        text,                             -- puesto / grupo del listado (COMMAND CENTER, DESARROLLO-DBA, ...)
    area         text not null,                    -- área del dashboard o grupo aparte
    reporta_a    text references personal(id_empleado),
    incluir      boolean not null default true,
    actualizado  timestamp not null default now()
);

alter table personal enable row level security;

-- Asistencias: copia de REPORTES_INCIDENCIAS.dbo.OBTENER_INFORME_EVENTOS (solo personal del listado),
-- cargada con etl/asistencias_to_supabase.py. Una fila por persona y día.
create table if not exists asistencias (
    id_empleado      text not null,
    fecha            date not null,
    incidencia       text,               -- código original (A, R, FA, VAC, DOL, I-M, ...)
    descripcion      text,
    estatus          text not null,      -- asistencia | retardo | falta | vacaciones | incapacidad | descanso | suspension | sin_registro
    inicio_jornada   time,
    fin_jornada      time,
    entrada          time,               -- primera checada (null = no checó)
    salida           time,               -- última checada (null = no checó)
    minutos_tarde    numeric,            -- entrada - inicio_jornada (puede ser negativo)
    retardo          boolean not null default false,   -- minutos_tarde > 15
    sin_entrada      boolean not null default false,   -- día laborado sin checada de entrada
    sin_salida       boolean not null default false,   -- día laborado sin checada de salida
    sin_horario      boolean not null default false,   -- día laborado sin inicio de jornada
    campana          text,
    puesto           text,
    reporta_a        text,               -- según el sistema de incidencias
    edificio         text,
    comentario       text,
    actualizado      timestamp not null default now(),
    primary key (id_empleado, fecha)
);

create index if not exists idx_asistencias_fecha on asistencias (fecha);
alter table asistencias enable row level security;
