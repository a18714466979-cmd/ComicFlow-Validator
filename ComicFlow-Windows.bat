@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
set "PYTHONUTF8=1"
where /q py
if errorlevel 1 goto fallback
py -3 -m src.windows_launcher "%~1"
set "COMICFLOW_EXIT=%errorlevel%"
goto complete

:fallback
where /q python
if errorlevel 1 goto missing_python
python -m src.windows_launcher "%~1"
set "COMICFLOW_EXIT=%errorlevel%"
goto complete

:missing_python
echo Python 3 is required. Install Python with Tkinter and the repository requirements.
set "COMICFLOW_EXIT=2"

:complete
popd
echo.
pause
exit /b %COMICFLOW_EXIT%
