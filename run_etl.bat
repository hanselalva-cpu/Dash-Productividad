@echo off
REM ETL a Supabase (Programador de tareas: "Dash Productividad - ETL ServiceDesk", 10, 12, 16 y 18 h).
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> "logs\etl.log"
".venv\Scripts\python.exe" -m etl.servicedesk_to_supabase >> "logs\etl.log" 2>&1
".venv\Scripts\python.exe" -m etl.asistencias_to_supabase >> "logs\etl.log" 2>&1
".venv\Scripts\python.exe" -m etl.proyectos_to_supabase >> "logs\etl.log" 2>&1
