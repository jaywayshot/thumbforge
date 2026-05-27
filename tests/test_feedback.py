"""
피드백 시스템 테스트 (네트워크 없음, 임시 워크스페이스로 격리)

검증
─ 기록 + variant_id 별 최신 의견 우선(덮어쓰기)
─ filter / aggregate(winner rate, 할인 유무, 피어슨)
─ jsonl 1MB 회전 + 데이터 무손실
─ generation 메타 영속화 → 피드백 메타 복원
─ API: POST 200/400/404, recent, stats, export.csv 형식
"""
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import feedback_store, job_store
from app.services.feedback_store import FeedbackEntry
from app.settings import settings


@contextmanager
def tmp_ws():
    """settings.workspace_dir 를 임시 디렉토리로 바꿔 피드백/jobs 를 격리하고 복원."""
    d = Path(tempfile.mkdtemp(prefix="fbtest_"))
    saved = settings.workspace_dir
    settings.workspace_dir = str(d)
    settings.ensure_dirs()
    try:
        yield d
    finally:
        settings.workspace_dir = saved
        shutil.rmtree(d, ignore_errors=True)


def _entry(variant_id="j1_v1", job_id="j1", **kw):
    base = dict(job_id=job_id, variant_id=variant_id, concept="coupang_sales",
                layout_used="huge_text_top", platform="coupang", text_provider="mock",
                ctr_estimate=80, feedback_type="winner")
    base.update(kw)
    return FeedbackEntry(**base)


# ───────── 저장소 ─────────

def test_record_and_latest_wins():
    with tmp_ws():
        feedback_store.record_feedback(_entry(feedback_type="winner"))
        feedback_store.record_feedback(_entry(feedback_type="loser"))  # 같은 variant 덮어쓰기
        items = feedback_store.list_feedback()
        assert len(items) == 1, items
        assert items[0]["feedback_type"] == "loser"  # 마지막 의견이 진실
        print("  ✓ 기록 + 최신 의견 우선(덮어쓰기)")


def test_filter():
    with tmp_ws():
        feedback_store.record_feedback(_entry(variant_id="j1_v1", concept="coupang_sales"))
        feedback_store.record_feedback(_entry(variant_id="j2_v1", job_id="j2", concept="premium_luxury"))
        got = feedback_store.list_feedback(concept="premium_luxury")
        assert len(got) == 1 and got[0]["variant_id"] == "j2_v1"
        print("  ✓ filter 동작")


def test_aggregate_winner_rate():
    with tmp_ws():
        # coupang_sales: winner 2, loser 1 → rate 2/3
        feedback_store.record_feedback(_entry(variant_id="a_v1", feedback_type="winner", concept="coupang_sales"))
        feedback_store.record_feedback(_entry(variant_id="a_v2", feedback_type="winner", concept="coupang_sales"))
        feedback_store.record_feedback(_entry(variant_id="a_v3", feedback_type="loser", concept="coupang_sales"))
        feedback_store.record_feedback(_entry(variant_id="a_v4", feedback_type="discard", concept="coupang_sales"))
        stats = feedback_store.aggregate_stats()
        cs = stats["by_concept"]["coupang_sales"]
        assert cs["winner"] == 2 and cs["loser"] == 1 and cs["discard"] == 1
        assert abs(cs["winner_rate"] - round(2 / 3, 4)) < 1e-9, cs
        assert stats["total_feedback"] == 4
        print(f"  ✓ winner rate 집계: {cs}")


def test_pearson_correlation():
    with tmp_ws():
        # 높은 CTR=winner, 낮은 CTR=loser → 양의 상관
        for i, (ctr, ft) in enumerate([(90, "winner"), (85, "winner"), (30, "loser"), (20, "loser")]):
            feedback_store.record_feedback(_entry(variant_id=f"p_v{i}", ctr_estimate=ctr, feedback_type=ft))
        stats = feedback_store.aggregate_stats()
        assert stats["ctr_vs_winner_pearson"] is not None
        assert stats["ctr_vs_winner_pearson"] > 0.5, stats["ctr_vs_winner_pearson"]
        assert stats["ctr_corr_sample_size"] == 4
        print(f"  ✓ 피어슨 상관: {stats['ctr_vs_winner_pearson']}")


def test_discount_split():
    with tmp_ws():
        feedback_store.record_feedback(_entry(variant_id="d_v1", has_discount=True, feedback_type="winner"))
        feedback_store.record_feedback(_entry(variant_id="d_v2", has_discount=False, feedback_type="loser"))
        d = feedback_store.aggregate_stats()["discount"]
        assert d["with_discount"]["winner"] == 1
        assert d["without_discount"]["loser"] == 1
        print("  ✓ 할인 유무 분리 집계")


def test_jsonl_rotation_no_data_loss():
    with tmp_ws():
        saved_max = feedback_store.MAX_BYTES
        feedback_store.MAX_BYTES = 500  # 회전 강제
        try:
            for i in range(40):
                feedback_store.record_feedback(_entry(variant_id=f"r_v{i}", user_note="x" * 30))
            rotated = list(feedback_store._dir().glob("feedback-*.jsonl"))
            assert rotated, "회전 파일이 생성되지 않음"
            # 모든 variant 가 보존되어야 함(무손실)
            all_entries = feedback_store._read_all()
            vids = {e["variant_id"] for e in all_entries}
            assert all(f"r_v{i}" in vids for i in range(40)), "회전 중 데이터 손실"
            assert len(feedback_store.list_feedback(limit=1000)) == 40
            print(f"  ✓ 1MB 회전 무손실: 회전파일 {len(rotated)}개, 40건 보존")
        finally:
            feedback_store.MAX_BYTES = saved_max


def test_global_variant_id_split():
    assert job_store.make_global_variant_id("abc123", "v1") == "abc123_v1"
    assert job_store.split_global_variant_id("abc123_v1") == ("abc123", "v1")
    print("  ✓ 전역 variant ID 합성/분해")


# ───────── API ─────────

def _seed_job():
    job_store.save_generation_meta(
        "job0001abcd", upload_id="up1", category="electronics",
        concept="tech_electronics", platform="coupang", text_provider="mock",
        variants={"v1": {"layout_used": "left_product_right_text", "headline": "초고속",
                         "sub_text": "당일배송", "badge": "HOT", "has_discount": True,
                         "ctr_estimate": 88}},
    )
    return "job0001abcd_v1"


def test_api_post_recovers_meta():
    with tmp_ws():
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        gid = _seed_job()
        r = client.post("/api/feedback", json={"variant_id": gid, "feedback_type": "winner"})
        assert r.status_code == 200, r.text
        assert "feedback_id" in r.json() and "recorded_at" in r.json()
        # 메타가 복원되어 기록됐는지
        items = feedback_store.list_feedback()
        assert items[0]["concept"] == "tech_electronics"
        assert items[0]["layout_used"] == "left_product_right_text"
        assert items[0]["ctr_estimate"] == 88 and items[0]["has_discount"] is True
        print("  ✓ API POST: 메타 자동 복원 기록")


def test_api_post_bad_type():
    with tmp_ws():
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        gid = _seed_job()
        r = client.post("/api/feedback", json={"variant_id": gid, "feedback_type": "love"})
        assert r.status_code == 400, r.text
        print("  ✓ API POST: 잘못된 feedback_type → 400")


def test_api_post_unknown_variant():
    with tmp_ws():
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r = client.post("/api/feedback", json={"variant_id": "nope_v9", "feedback_type": "winner"})
        assert r.status_code == 404, r.text
        print("  ✓ API POST: 없는 variant → 404")


def test_api_recent_and_stats():
    with tmp_ws():
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        gid = _seed_job()
        client.post("/api/feedback", json={"variant_id": gid, "feedback_type": "winner"})
        r = client.get("/api/feedback/recent?limit=10")
        assert r.status_code == 200 and len(r.json()["items"]) == 1
        s = client.get("/api/feedback/stats")
        assert s.status_code == 200 and s.json()["total_feedback"] == 1
        print("  ✓ API recent/stats")


def test_api_csv_export():
    with tmp_ws():
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        gid = _seed_job()
        client.post("/api/feedback", json={"variant_id": gid, "feedback_type": "winner"})
        r = client.get("/api/feedback/export.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        text = r.content.decode("utf-8-sig")
        lines = [l for l in text.splitlines() if l.strip()]
        assert "feedback_id" in lines[0] and "concept" in lines[0]  # 헤더
        assert "tech_electronics" in text  # 데이터
        assert len(lines) == 2  # 헤더 + 1건
        print("  ✓ API CSV export 형식")


if __name__ == "__main__":
    print("\n=== 피드백 시스템 테스트 ===")
    test_record_and_latest_wins()
    test_filter()
    test_aggregate_winner_rate()
    test_pearson_correlation()
    test_discount_split()
    test_jsonl_rotation_no_data_loss()
    test_global_variant_id_split()
    test_api_post_recovers_meta()
    test_api_post_bad_type()
    test_api_post_unknown_variant()
    test_api_recent_and_stats()
    test_api_csv_export()
    print("\n✅ 피드백 시스템 테스트 전체 통과")
