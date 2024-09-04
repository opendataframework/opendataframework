curl -X POST \
  -H 'Authorization':"Bearer $access_token" \
  -H "Content-type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "database_name": "PostgreSQL",
    "engine": "postgresql",
    "configuration_method": "dynamic_form",
    "engine_information": {
      "disable_ssh_tunneling": false,
      "supports_file_upload": true
    },
    "driver": "psycopg2",
    "extra": "{\"allows_virtual_table_explore\":true}",
    "expose_in_sqllab": true,
    "parameters": {
        "host": "host.docker.internal",
        "port": "5432",
        "database": "project_name",
        "username": "admin",
        "password": "admin"
        },
    "masked_encrypted_extra": "{}"
    }' \
  "http://localhost:8088/api/v1/database/" \
