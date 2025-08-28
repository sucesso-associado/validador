@echo off

REM Navega para o diretório do projeto (onde este .bat está)
cd /d "%~dp0"

REM Ativa o ambiente virtual
call venv\Scripts\activate.bat

REM Inicia o servidor Flask
REM O caminho para main.py é relativo à raiz do projeto (onde o .bat está)
python src\main.py

pause


