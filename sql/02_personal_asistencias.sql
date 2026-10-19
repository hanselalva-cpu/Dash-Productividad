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
