"""
CLI 배치 생성 도구 스모크 테스트
─ 임시 입력 폴더에 가짜 제품 2장 → process_one/run_cli 로 생성 → 출력 파일 확인
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

from scripts.generate_cli import collect_inputs, process_one, run_cli


def _make_product(path: Path, color=(220, 50, 50)):
    im = Image.new("RGB", (320, 320), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 280, 280], fill=color)
    im.save(path, "PNG")


def test_collect_inputs(tmp_path=None):
    d = Path(tempfile.mkdtemp())
    _make_product(d / "a.png")
    _make_product(d / "b.jpg", color=(50, 120, 220))
    (d / "notes.txt").write_text("ignore me", encoding="utf-8")
    found = collect_inputs(d)
    assert len(found) == 2, found
    # 단일 파일도
    assert collect_inputs(d / "a.png") == [d / "a.png"]
    print(f"  ✓ collect_inputs: {len(found)}장 (txt 무시)")


def test_process_one():
    d = Path(tempfile.mkdtemp())
    out = Path(tempfile.mkdtemp())
    src = d / "widget.png"
    _make_product(src)
    results = process_one(src, "white_minimal", "coupang", 3, out)
    assert len(results) == 3
    for r in results:
        assert Path(r["output"]).exists()
        assert 0 <= r["ctr_score"] <= 100
    print(f"  ✓ process_one: {len(results)}장 생성")


def test_run_cli():
    d = Path(tempfile.mkdtemp())
    out = Path(tempfile.mkdtemp())
    _make_product(d / "p1.png")
    _make_product(d / "p2.png", color=(60, 200, 90))
    code = run_cli(["--input", str(d), "--output", str(out),
                    "--concept", "white_minimal", "--variants", "2"])
    assert code == 0
    pngs = list(out.glob("*.png"))
    assert len(pngs) == 4, f"기대 4장(2제품×2), 실제 {len(pngs)}"
    print(f"  ✓ run_cli: {len(pngs)}장 출력")


def test_run_cli_empty_input():
    d = Path(tempfile.mkdtemp())  # 이미지 없음
    code = run_cli(["--input", str(d), "--output", str(Path(tempfile.mkdtemp()))])
    assert code == 1
    print("  ✓ 빈 입력 → exit 1")


if __name__ == "__main__":
    print("\n=== CLI 배치 생성 테스트 ===")
    test_collect_inputs()
    test_process_one()
    test_run_cli()
    test_run_cli_empty_input()
    print("\n✅ CLI 테스트 전체 통과")
