echo ">> Setting up Superset"
docker exec -it project_name_superset superset fab create-admin \
  --username admin \
  --firstname Superset \
  --lastname Admin \
  --email admin@superset.com \
  --password admin

docker exec -it project_name_superset superset db upgrade
docker exec -it project_name_superset superset init

json=$(curl -k 'http://localhost:8088/api/v1/security/login' \
        -X POST -H 'Content-Type: application/json' \
        -d '{"password": "admin", "provider": "db", "refresh": true, "username": "admin"}') \
&& access_token=$(echo $json | sed "s/{.*\"access_token\":\"\([^\"]*\).*}/\1/g") \
&& echo "access_token = $access_token" \
