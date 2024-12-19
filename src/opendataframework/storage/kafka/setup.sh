echo ">> Setting up Kafka"
docker exec -it project_name_kafka bash -c '/opt/kafka/bin/kafka-topics.sh --bootstrap-server project_name-kafka:9092 --create --topic entities'
