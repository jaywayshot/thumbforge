@echo off
chcp 65001 > nul
setlocal

echo.
echo ============================================================
echo  ThumbForge 초기 셋업 (Windows)
echo ============================================================
echo.

REM Python 확인
where python > nul 2>&1
if errorlevel 1 (
    echo [X] Python 이 설치되지 않았습니다.
    echo     https://www.python.org/downloads/ 에서 Python 3.10+ 설치 후 다시 실행하세요.
    pause
    exit /b 1
)

python --version

REM 가상환경 생성
if not exist .venv (
    echo.
    echo [1/3] 가상환경 생성 중...
    python -m venv .venv
    if errorlevel 1 (
        echo [X] 가상환경 생성 실패
        pause
        exit /b 1
    )
)

REM 활성화 + pip 업그레이드
echo.
echo [2/3] pip 업그레이드 + 의존성 설치 중... (수 분 소요 가능)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] 의존성 설치 실패
    pause
    exit /b 1
)

REM .env 자동 생성
if not exist .env (
    echo.
    echo [3/3] .env 파일 생성 중 (mock 모드로 시작)
    copy .env.example .env > nul
)

echo.
echo ============================================================
echo  ✅ 셋업 완료!
echo  이제 run.bat 을 실행하세요.
echo ============================================================
echo.
pause
