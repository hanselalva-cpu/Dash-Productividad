-- Proyectos: copia de los concentrados de proyectos de las PMs (Excel en data/proyectos/),
-- cargada con etl/proyectos_to_supabase.py. Cada carga reemplaza el contenido completo.
create table if not exists proyectos (
    proyecto_id         text primary key,      -- portafolio + nombre del proyecto, normalizado
    portafolio          text not null,         -- PM dueña del concentrado
    portafolio_id       text,                  -- id_empleado de la PM (data/alias_personas.csv)
    proyecto            text not null,
    objetivo            text,
    estado              text not null
                        check (estado in ('En desarrollo', 'En pruebas', 'En espera', 'Terminado', 'Cancelado')),
    estado_origen       text,                  -- tal como viene en el Excel (Completo, En curso, Pruebas, ...)
    avance              numeric,               -- 0 a 1
    inicio              date,
    fin                 date,
    solicitante         text,
    responsables_texto  text,                  -- texto original de la columna Responsables
    situacion           text,                  -- Comentarios actuales
    archivo             text,
    actualizado         timestamp not null default now()
);

create table if not exists proyecto_asignaciones (
    proyecto_id  text not null references proyectos(proyecto_id) on delete cascade,
    persona      text not null,                -- nombre tal como viene en el Excel
    id_empleado  text,                         -- null si no se pudo homologar
    rol          text not null
                 check (rol in ('Desarrollo', 'Base de datos', 'Coordinación', 'Command center')),
    primary key (proyecto_id, persona, rol)
);

alter table proyectos              enable row level security;
alter table proyecto_asignaciones  enable row level security;
