@echo off
REM LinkedIn Topic Scanner - denní automatický scan
REM Spouštěno přes Windows Task Scheduler denně v 8:00

cd /d C:\Users\thomi\projects\linkedin-topic-scanner
python -m src.cli scan --email >> data\scan_log.txt 2>&1
