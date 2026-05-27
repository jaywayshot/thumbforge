@echo off
chcp 65001 > nul
setlocal

REM .venv 없으면 셋업 자동 실행
if not exist .venv\Scripts\python.exe (
    echo .venv 가 없어 setup.bat 을 먼저 실행합니다...
    call setup.bat
)

call .venv\Scripts\activate.bat

REM 브라우저 자동 오픈 (3초 후)
start "" /b cmd /c "timeout /t 3 /nobreak > nul && start http://127.0.0.1:8000"

echo.
echo ============================================================
echo  ThumbForge 서버 시작
echo  http://127.0.0.1:8000
echo  종료: Ctrl+C
echo ============================================================
echo.

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
