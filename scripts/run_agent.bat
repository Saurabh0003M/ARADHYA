@echo off
call venv\Scripts\activate.bat
echo Starting Aradhya Agent...
python -m core.agent.aradhya
pause
