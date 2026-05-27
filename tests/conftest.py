"""
pytest 공통 설정.

- 프로젝트 루트를 sys.path 에 추가 (테스트 어디서 실행하든 app 임포트 가능)
- Windows 콘솔(cp949)에서 ✓ / → 같은 문자 출력 시 UnicodeEncodeError 방지.
  (PYTHONUTF8=1 을 매번 주지 않아도 pytest -s 로 돌 때 깨지지 않게)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
