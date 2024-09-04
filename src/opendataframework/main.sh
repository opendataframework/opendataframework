echo "Open"
echo "Data"
echo "Framework"

echo ""
echo "WORKDIR:"
cd platform
pwd

chmod +x ./build.sh && chmod +x ./start.sh && chmod +x ./setup.sh && chmod +x ./stop.sh

echo ""
echo "Building project_name ..."
./build.sh

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

echo ""
echo "Setting up virtual environment in project_name ..."
chmod +x ./env.sh
source ./env.sh

echo "Done."
