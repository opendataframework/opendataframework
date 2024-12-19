echo ">> Setting up Kafka"
docker exec -it project_name_kafka bash -c '/opt/kafka/bin/kafka-topics.sh --bootstrap-server project_name-kafka --create --topic entities'
