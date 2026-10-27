@echo off
setlocal
set PYTHONPATH=%~dp0vendor
py -3 -m mcl %*
