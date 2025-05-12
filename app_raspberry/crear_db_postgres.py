import psycopg2
from psycopg2 import sql

# Configuración inicial
PG_HOST = "localhost"
PG_ADMIN_USER = "postgres"
PG_ADMIN_PASSWORD = "Madremia902"  # Cambiar por la contraseña real del superusuario

DB_NAME = "logs"
DB_USER = "logs_users"
DB_PASSWORD = "Madremia902"

# Lista de fuentes de logs para las que se crearán tablas
# Modifica esta lista según los "archivos de log" o servicios que tengas
LOG_SOURCES = [
    "camera_service",          # Para mantener la tabla original si es necesario
    "fastapi_service",
    "guardar_horario",
    "start_threads"
]

# Conexión al servidor PostgreSQL como administrador
def create_database_and_user():
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname="postgres", user=PG_ADMIN_USER, password=PG_ADMIN_PASSWORD)
        conn.autocommit = True
        cursor = conn.cursor()

        # Crear base de datos
        cursor.execute(f"CREATE DATABASE {DB_NAME};")
        print(f"✅ Base de datos '{DB_NAME}' creada.")

        # Crear usuario
        cursor.execute(f"CREATE USER {DB_USER} WITH ENCRYPTED PASSWORD '{DB_PASSWORD}';")
        print(f"✅ Usuario '{DB_USER}' creado.")

        # Otorgar permisos
        cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};")
        print(f"✅ Permisos otorgados a '{DB_USER}' sobre '{DB_NAME}'.")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"❌ Error creando base de datos o usuario: {e}")

def create_tables():
    try:
        conn = psycopg2.connect(host=PG_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
        cursor = conn.cursor()

        for source_name in LOG_SOURCES:
            table_name = f"{source_name}_logs"
            # Usar sql.Identifier para el nombre de la tabla para seguridad y correcta sintaxis
            create_table_query = sql.SQL("""
            CREATE TABLE IF NOT EXISTS {table} (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                level VARCHAR(10),
                message TEXT
            );
            """).format(table=sql.Identifier(table_name))

            cursor.execute(create_table_query)
            print(f"✅ Tabla '{table_name}' creada o ya existente.")

        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ {len(LOG_SOURCES)} tablas de logs creadas/verificadas.")
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")

if __name__ == "__main__":
    create_database_and_user()
    create_tables()