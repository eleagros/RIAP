VENV_DIR="venv"
if [ -d "$VENV_DIR" ]; then
    echo "Directory '$VENV_DIR' already exists. Skipping git clone."
else
    python3.9 -m pip install pip --upgrade
    python3.9 -m venv venv
fi

source venv/bin/activate
pip install -e .