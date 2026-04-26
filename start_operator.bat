@echo off
:: start_operator.bat - Legacy launcher (silent, small mode by default)
:: Use start_small.bat or start_homelab.bat for explicit mode selection

set JARVIS_MODE=small
cscript //nologo start_operator_hidden.vbs
