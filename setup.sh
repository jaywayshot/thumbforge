#!/usr/bin/env bash
set -e

echo
echo "============================================================"
echo "  ThumbForge 초기 셋업 (macOS / Linux)"
echo "============================================================"
echo

if ! command -v python3 > /dev/null 2>&1; then
  echo "[X] python3 가 설치되지 않았습니다."
  echo "    macOS: brew install python@3.11"
  echo "    Linux: sudo apt install python3 python3-venv python3-pip"
  exit 1
fi

python3 --version

if [ ! -d ".venv" ]; then
  echo
  echo "[1/3] 가상환경 생성 중..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo
echo "[2/3] pip 업그레이드 + 의존성 설치 중..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
  echo
  echo "[3/3] .env 파일 생성 (mock 모드)"
  cp .env.example .env
fi

echo
echo "============================================================"
echo "  ✅ 셋업 완료. ./run.sh 로 실행하세요."
echo "============================================================"
