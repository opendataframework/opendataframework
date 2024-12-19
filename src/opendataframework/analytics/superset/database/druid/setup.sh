curl -X POST \
  -H 'Authorization':"Bearer $access_token" \
  -H "Content-type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "database_name": "Apache Druid",
    "engine": "druid",
    "configuration_method": "sqlalchemy_form",
    "engine_information": {
      "disable_ssh_tunneling": false,
      "supports_file_upload": true
    },
    "sqlalchemy_uri_placeholder": "engine+driver://user:password@host:port/dbname[?key=value&key=value...]",
    "extra": "{\"allows_virtual_table_explore\":true}",
    "expose_in_sqllab": true,
    "sqlalchemy_uri": "druid://host.docker.internal:8082/druid/v2/sql/"
    }' \
  "http://localhost:8088/api/v1/database/" \
