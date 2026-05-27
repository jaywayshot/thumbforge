"""
FastAPI 라우트 통합 테스트 (TestClient, 실제 네트워크 없음)
─ /healthz, /api/concepts, /api/platforms
─ /api/brands CRUD
─ /api/upload → /api/generate → 결과 파일 다운로드
─ /api/bulk/upload → 상태 폴링 → 결과 ZIP
"""
import io
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _png_bytes(size=(400, 400), color=(255, 255, 255), ellipse=(220, 50, 50)) -> bytes:
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    pad = size[0] // 8
    d.ellipse([pad, pad, size[0] - pad, size[1] - pad], fill=ellipse)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _zip_bytes(n=2) -> bytes:
    colors = [(220, 50, 50), (50, 180, 90), (50, 90, 220)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(n):
            zf.writestr(f"prod_{i}.png", _png_bytes(ellipse=colors[i % len(colors)]))
    return buf.getvalue()


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    print(f"  ✓ /healthz: {body}")


def test_concepts_and_platforms():
    rc = client.get("/api/concepts")
    assert rc.status_code == 200
    concepts = rc.json()
    assert isinstance(concepts, dict) and len(concepts) > 0
    assert all("label" in v for v in concepts.values())

    rp = client.get("/api/platforms")
    assert rp.status_code == 200
    platforms = rp.json()
    assert "coupang" in platforms
    assert "sizes" in platforms["coupang"]
    print(f"  ✓ concepts={len(concepts)}개, platforms={len(platforms)}개")


def test_brand_crud():
    # 생성
    r = client.post("/api/brands", json={"name": "API 테스트 브랜드"})
    assert r.status_code == 200, r.text
    brand = r.json()
    bid = brand["brand_id"]
    assert bid and brand["name"] == "API 테스트 브랜드"

    # 목록에 포함
    r = client.get("/api/brands")
    assert r.status_code == 200
    assert any(b["brand_id"] == bid for b in r.json())

    # 단건 조회
    r = client.get(f"/api/brands/{bid}")
    assert r.status_code == 200

    # 수정 (PATCH)
    r = client.patch(f"/api/brands/{bid}", json={"accent_color": "#123456"})
    assert r.status_code == 200 and r.json()["accent_color"] == "#123456"

    # 삭제
    r = client.delete(f"/api/brands/{bid}")
    assert r.status_code == 200 and r.json()["ok"] is True

    # 삭제 후 404
    r = client.get(f"/api/brands/{bid}")
    assert r.status_code == 404
    print(f"  ✓ 브랜드 CRUD: 생성/조회/수정/삭제/404 ({bid})")


def test_upload_generate_download():
    # 업로드
    files = {"file": ("product.png", _png_bytes(), "image/png")}
    r = client.post("/api/upload", files=files)
    assert r.status_code == 200, r.text
    up = r.json()
    upload_id = up["upload_id"]
    assert upload_id and up["width"] == 400 and up["height"] == 400

    # 생성 (2 variants)
    payload = {
        "upload_id": upload_id,
        "concept": "white_minimal",
        "platform": "coupang",
        "variants": 2,
        "text": {"headline": "오늘의 추천", "sub_text": "빠른 배송", "badge": "NEW"},
    }
    r = client.post("/api/generate", json=payload)
    assert r.status_code == 200, r.text
    gen = r.json()
    assert len(gen["variants"]) == 2
    for v in gen["variants"]:
        assert 0 <= v["ctr_score"] <= 100
        assert v["file_url"].startswith("/files/")

    # 결과 파일 다운로드
    file_url = gen["variants"][0]["file_url"]
    r = client.get(file_url)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    print(f"  ✓ upload→generate(2 variants)→download OK (job {gen['job_id']})")


def test_bulk_flow():
    files = {"file": ("products.zip", _zip_bytes(2), "application/zip")}
    data = {
        "concept": "white_minimal",
        "platform": "coupang",
        "variants_per_image": "1",
        "text_json": "{}",
    }
    r = client.post("/api/bulk/upload", files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    job_id = body["job_id"]
    assert job_id and body["status"] == "pending"

    # 상태 폴링 (백그라운드 스레드)
    final = None
    for _ in range(120):
        s = client.get(f"/api/bulk/status/{job_id}")
        assert s.status_code == 200
        final = s.json()
        if final["status"] in ("success", "failed"):
            break
        time.sleep(0.5)
    assert final and final["status"] == "success", f"bulk 실패: {final}"

    # 결과 ZIP
    r = client.get(f"/api/bulk/result/{job_id}.zip")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    print(f"  ✓ bulk upload→status({final['status']})→result.zip OK (job {job_id})")


if __name__ == "__main__":
    print("\n=== API 통합 테스트 ===")
    test_healthz()
    test_concepts_and_platforms()
    test_brand_crud()
    test_upload_generate_download()
    test_bulk_flow()
    print("\n✅ API 통합 테스트 전체 통과")
