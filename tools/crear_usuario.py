"""Genera la línea de Secrets [usuarios] para dar acceso con contraseña.

Uso: python -m tools.crear_usuario
Pide correo y contraseña (no se muestra al escribir) e imprime la línea para pegar en
`.streamlit/secrets.toml` y en los Secrets de Streamlit Cloud, sección [usuarios].
El correo también debe estar en [accesos] con su id_empleado.
"""

import getpass
import os

from tablero.acceso import hash_contrasena


def main() -> None:
    correo = input("Correo: ").strip().lower()
    contrasena = getpass.getpass("Contraseña (mín. 10 caracteres): ")
    if len(contrasena) < 10:
        raise SystemExit("La contraseña debe tener al menos 10 caracteres.")
    if getpass.getpass("Repite la contraseña: ") != contrasena:
        raise SystemExit("Las contraseñas no coinciden.")
    print("\nPega esta línea en la sección [usuarios]:\n")
    print(f'"{correo}" = "{hash_contrasena(contrasena, os.urandom(16))}"')


if __name__ == "__main__":
    main()
