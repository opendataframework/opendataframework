echo ">> Setting up Postgres"
docker exec -i project_name_postgres psql -U postgres <<EOF
CREATE USER admin WITH PASSWORD 'admin';
CREATE DATABASE project_name OWNER admin;
EOF
