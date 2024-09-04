echo "> creating virtual environment (.venv)"
python3 -m venv .venv

source .venv/bin/activate
echo "> virtual environment (.venv) activated"

echo "> python used:"
which python

echo "> install requirements"
pip install -r requirements.txt
