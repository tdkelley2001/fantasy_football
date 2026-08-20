@echo off

echo Checking for virtual environment...

IF NOT EXIST "venv\" (
    echo Creating virtual environment...
    python -m venv venv
) ELSE (
    echo Virtual environment already exists.
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing Python packages from requirements.txt...
pip install --upgrade pip
pip install -r requirements.txt

echo Setup complete. Your environment is ready!
pause
