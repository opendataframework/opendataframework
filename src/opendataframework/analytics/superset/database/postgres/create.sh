curl -X POST \
  -H 'Authorization':"Bearer $access_token" \
  -H "Content-type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "database": 1,
    "schema": "public",
    "table_name": "table-name"
    }' \
  "http://localhost:8088/api/v1/dataset/"
