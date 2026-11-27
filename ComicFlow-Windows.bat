@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" goto try_path
".venv\Scripts\python.exe" -c "import tkinter, PIL, numpy" >nul 2>&1
if errorlevel 1 goto try_path
".venv\Scripts\python.exe" -m src.windows_launcher "%~1"
set "COMICFLOW_EXIT=%errorlevel%"
goto complete

:try_path
where /q python
if errorlevel 1 goto fallback
python -c "import tkinter, PIL, numpy" >nul 2>&1
if errorlevel 1 goto fallback
python -m src.windows_launcher "%~1"
set "COMICFLOW_EXIT=%errorlevel%"
goto complete

:fallback
where /q py
if errorlevel 1 goto missing_dependencies
py -3 -c "import tkinter, PIL, numpy" >nul 2>&1
if errorlevel 1 goto missing_dependencies
py -3 -m src.windows_launcher "%~1"
set "COMICFLOW_EXIT=%errorlevel%"
goto complete

:missing_dependencies
echo No Python interpreter with Tkinter, Pillow, and NumPy was found.
echo Install Python 3 with Tcl/Tk, then run: python -m pip install -r requirements.txt
set "COMICFLOW_EXIT=2"

:complete
popd
if not "%COMICFLOW_EXIT%"=="0" pause
exit /b %COMICFLOW_EXIT%
