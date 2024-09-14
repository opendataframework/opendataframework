echo "Open"
echo "Data"
echo "Framework"

echo ""
echo "WORKDIR:"
cd platform
pwd

chmod +x ./start.sh && chmod +x ./setup.sh && chmod +x ./stop.sh

echo ""
echo "Starting project_name ..."
./start.sh

echo ""
echo "Wating ..."
sleep 30

echo ""
echo "Setting up project_name ..."
./setup.sh

echo ""
echo "Wating ..."
sleep 10

echo ""
echo "WORKDIR:"
cd ..
pwd

echo "Done."
