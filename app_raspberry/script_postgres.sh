#!/bin/bash

# --- Configuración ---
POSTGRES_PASSWORD="Madremia902"

echo "🔄 Actualizando el sistema..."
sudo apt update && sudo apt upgrade -y

echo "🔄 Instalando PostgreSQL..."
sudo apt install postgresql postgresql-contrib -y

echo "🔄 Configurando contraseña para el usuario postgres..."
sudo -u postgres psql -c "ALTER USER postgres WITH PASSWORD '${POSTGRES_PASSWORD}';"

echo "🔄 Configurando pg_hba.conf para usar md5..."
PG_HBA=$(find /etc/postgresql -name pg_hba.conf)
if [ -f "$PG_HBA" ]; then
    sudo sed -i "s/local\s\+all\s\+postgres\s\+peer/local   all             postgres                                md5/g" "$PG_HBA"
else
    echo "❌ No se encontró pg_hba.conf"
    exit 1
fi

echo "🔄 Reiniciando PostgreSQL..."
sudo systemctl restart postgresql

echo "✅ PostgreSQL instalado y configurado con usuario 'postgres' y contraseña '${POSTGRES_PASSWORD}'."
echo "Puedes probar con: psql -U postgres -h localhost -d postgres"