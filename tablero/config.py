"""Configuración compartida entre el ETL y el dashboard (sin dependencias de Streamlit)."""

AREAS = ["Desarrollo", "Eficiencia", "Soporte", "Base de datos", "Gestor de claves", "PMS",
         "Seguridad de la información"]

# Áreas sin tickets (se miden asistencia y, si aplica, proyectos).
AREAS_SIN_FUENTE = {
    "PMS": "Fisgón (pendiente de integrar)",
}

# dbo.Edificio en ServiceDesk
EDIFICIOS = {1: "Cantarranas", 2: "Piramide", 3: "Plaza Guadalupe", 4: "Plaza Sur", 5: "Edificio Reforma"}

# dbo.Subarea.SubareaId que forman cada área del dashboard
SUBAREAS_POR_AREA = {
    "Desarrollo": [1],                                      # Desarrollo de Software
    "Base de datos": [2],                                   # BASE DE DATOS
    "Soporte": [3, 4, 5],                                   # Soporte; Servidores, Redes, WiFi; Telefonía, Marcadores
    "Gestor de claves": [28, 29, 30, 31, 32, 33, 34, 35, 36, 43],  # Area 36
    "Eficiencia": [45, 46, 47, 48,                          # Area 38 Eficiencia Operativa
                   19, 37, 38, 39, 40, 41, 42],             # Area 27 Command Center
    "Seguridad de la información": [6],                     # Area 22: Gestión de Incidentes
}

# Meta de resolución en días naturales por prioridad. ServiceDesk no trae SLA ni hora de
# creación (FechaCreacion es solo fecha), así que se mide desde las 00:00 del día de creación.
SLA_DIAS = {"Alta": 1, "Media": 2, "Baja": 3}
SLA_DIAS_DEFAULT = 3

# Asistencias (REPORTES_INCIDENCIAS.dbo.OBTENER_INFORME_EVENTOS)
TOLERANCIA_RETARDO_MIN = 15  # retardo = entrada más de 15 min después de InicioJornada

# Código de incidencia -> estatus del dashboard
ESTATUS_INCIDENCIA = {
    "A": "asistencia",
    "R": "asistencia",   # el SP marca R desde el primer minuto; el retardo se recalcula con la tolerancia
    "TC": "asistencia",  # trabajo con cliente
    "FA": "falta",
    "VAC": "vacaciones",
    "VAC-E": "vacaciones",
    "I-M": "incapacidad",
    "INC": "incapacidad",
    "DOL": "descanso",
    "DOG": "descanso",
    "SUS": "suspension",
    "X": "sin_registro",
}
# Días que cuentan para % asistencia (descansos, vacaciones e incapacidades no cuentan)
ESTATUS_LABORABLE = ["asistencia", "retardo", "falta", "suspension", "sin_registro"]
