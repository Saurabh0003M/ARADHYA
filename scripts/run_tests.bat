@echo off
call venv\Scripts\activate.bat
echo Running tests...
pytest tests/ -v --cov=src --cov=core
pause
