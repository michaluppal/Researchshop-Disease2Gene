@echo off
REM Double-click this file in Explorer to launch the pipeline viewer's live server.
setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%..\..\.."

set PY=python
if exist "pipeline\.venv\Scripts\python.exe" set PY=pipeline\.venv\Scripts\python.exe

echo -^> Pipeline Viewer launcher
echo   repo root: %CD%
echo   python:    %PY%
echo.

start "" timeout /t 2 /nobreak >nul ^&^& start "" "http://localhost:8765/"

"%PY%" publication\figures\pipeline-viewer\serve.py
