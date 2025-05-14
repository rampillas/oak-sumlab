import psycopg2
from psycopg2 import sql

# Configuración inicial
PG_HOST = "localhost"
PG_ADMIN_USER = "postgres"
PG_ADMIN_PASSWORD = "Madremia902"  # Cambiar por la contraseña real del superusuario

DB_NAME = "logs"
DB_USER = "postgres"

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

        # Crear tabla detections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                vehicle_id TEXT,
                x_position REAL,
                y_position REAL,
                direction TEXT,
                image BYTEA
            );
        """)
        print("✅ Tabla 'detections' creada o ya existente.")

        # Crear tabla config
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                id SERIAL PRIMARY KEY,
                send_image BOOLEAN,
                refresh_rate REAL
            );
        """)
        print("✅ Tabla 'config' creada o ya existente.")

        # Crear tabla preview_images
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS preview_images (
                id SERIAL PRIMARY KEY,
                image BYTEA
            );
        """)
        print("✅ Tabla 'preview_images' creada o ya existente.")

        # Insertar fila con id=1 en config si no existe
        cursor.execute("""
            INSERT INTO config (id, send_image, refresh_rate)
            VALUES (1, FALSE, 0)
            ON CONFLICT (id) DO NOTHING;
        """)

        conn.commit()
        cursor.close()
        conn.close()
        print(f"✅ {len(LOG_SOURCES)} tablas de logs creadas/verificadas.")
    except Exception as e:
        print(f"❌ Error creando tablas: {e}")

if __name__ == "__main__":
    create_database_and_user()
    create_tables()