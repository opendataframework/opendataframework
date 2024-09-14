echo "Open"
echo "Data"
echo "Framework"

echo ""
echo "WORKDIR:"
cd platform
pwd

chmod +x ./setup.sh

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
