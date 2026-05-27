#!/usr/bin/env bash
set -e

if [ ! -f ".venv/bin/python" ]; then
  echo ".venv 가 없어 setup.sh 를 먼저 실행합니다..."
  bash setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# 브라우저 자동 오픈 (3초 후, 백그라운드)
(
  sleep 3
  if [ "$(uname)" = "Darwin" ]; then
    open http://127.0.0.1:8000 || true
  elif command -v xdg-open > /dev/null; then
    xdg-open http://127.0.0.1:8000 || true
  fi
) &

echo
echo "============================================================"
echo "  ThumbForge 서버 시작"
echo "  http://127.0.0.1:8000"
echo "  종료: Ctrl+C"
echo "============================================================"
echo

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
