@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"
set "CHECK_PY=import sys, tkinter; sys.exit(sys.version_info[:2] < (3, 11))"
set "SETUP_RESULT=1"

if exist ".venv\Scripts\python.exe" goto install
if exist ".venv\pyvenv.cfg" goto invalid_environment

py -3.13 -c "%CHECK_PY%" >nul 2>&1
if not errorlevel 1 goto use_py313
python -c "%CHECK_PY%" >nul 2>&1
if not errorlevel 1 goto use_python
py -3 -c "%CHECK_PY%" >nul 2>&1
if not errorlevel 1 goto use_py
echo Install Python 3.13 with Tcl/Tk from python.org and run this setup again.
goto finish

:use_py313
py -3.13 -m venv ".venv"
goto created

:use_python
python -m venv ".venv"
goto created

:use_py
py -3 -m venv ".venv"

:created
if errorlevel 1 (
  echo Couldn't create the local .venv. Check Python's venv component and the folder write permissions.
  goto finish
)

:install
".venv\Scripts\python.exe" -c "%CHECK_PY%" >nul 2>&1
if errorlevel 1 goto invalid_environment
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-runtime.txt
if errorlevel 1 (
  echo Dependency installation failed. Check the pip output and the network, then run setup again.
  goto finish
)
".venv\Scripts\python.exe" -c "import tkinter, PIL, numpy, imageio_ffmpeg, webview"
if errorlevel 1 goto invalid_environment
echo COMICFLOW_SETUP_OK
echo Start ComicFlow-Windows.bat. You can drop a ZIP or a .cfproject onto it.
set "SETUP_RESULT=0"
goto finish

:invalid_environment
echo The existing .venv cannot use the required Python or Tcl/Tk. Rename it and run this setup again.

:finish
popd
if /I not "%~1"=="--no-pause" pause
exit /b %SETUP_RESULT%
