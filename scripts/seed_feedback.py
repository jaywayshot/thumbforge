"""
피드백 데이터 시드 (수동 실행 전용 — 통계 화면 확인용)

가짜 generation 메타데이터 20건 + 피드백 60건을 만들어 "성과 분석" 탭이
실제로 어떻게 보이는지 확인할 수 있게 한다. 시드 데이터는 job_id 가 "seedjob" 으로
시작하므로 --reset 으로 깔끔히 제거할 수 있다(실제 피드백은 보존).

사용법:
  python scripts/seed_feedback.py           # 시드 생성
  python scripts/seed_feedback.py --reset   # 시드 데이터만 삭제

주의: 외부 전송 없음. workspace/feedback/, workspace/jobs/ 에만 기록.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import feedback_store, job_store
from app.services.feedback_store import FeedbackEntry
from app.settings import settings

SEED_PREFIX = "seedjob"

CONCEPTS = ["coupang_sales", "premium_luxury", "white_minimal", "tech_electronics",
            "discount_event", "smartstore_emotional"]
LAYOUTS = ["left_product_right_text", "center_product", "huge_text_top",
           "huge_center_product", "diagonal"]
CATEGORIES = ["electronics", "beauty", "health_food", "fashion"]
PROVIDERS = ["mock", "openai", "anthropic"]


def _reset() -> None:
    # 1) 시드 job 메타 삭제
    removed_jobs = 0
    for p in settings.jobs_path.glob(f"{SEED_PREFIX}*.json"):
        p.unlink(); removed_jobs += 1
    # 2) 피드백 파일에서 시드 항목 제거(실제 데이터 보존) 후 재작성
    all_entries = feedback_store._read_all()
    kept = [e for e in all_entries if not str(e.get("job_id", "")).startswith(SEED_PREFIX)]
    removed_fb = len(all_entries) - len(kept)
    for f in feedback_store._all_files():
        f.unlink()
    if kept:
        with open(feedback_store._current_file(), "w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"리셋 완료: 시드 job {removed_jobs}건, 시드 피드백 {removed_fb}건 삭제 (실제 데이터 {len(kept)}건 보존)")


def _seed() -> None:
    rng = random.Random(42)
    settings.ensure_dirs()

    # 1) 20개 generation 메타 (각 1~3 variant)
    variant_pool = []  # (global_id, concept, has_discount, ctr)
    for i in range(20):
        job_id = f"{SEED_PREFIX}{i:04d}"
        concept = rng.choice(CONCEPTS)
        category = rng.choice(CATEGORIES)
        provider = rng.choice(PROVIDERS)
        nvar = rng.randint(1, 3)
        variants = {}
        for j in range(nvar):
            vid = f"v{j+1}"
            has_disc = rng.random() < 0.5
            ctr = rng.randint(40, 99)
            variants[vid] = {
                "layout_used": rng.choice(LAYOUTS),
                "headline": "오늘의 추천", "sub_text": "빠른 배송", "badge": "BEST",
                "has_discount": has_disc, "ctr_estimate": ctr,
            }
            variant_pool.append(job_store.make_global_variant_id(job_id, vid))
        job_store.save_generation_meta(
            job_id, upload_id=f"up{i}", category=category, concept=concept,
            platform="coupang", text_provider=provider, variants=variants,
        )

    # 2) 60건 피드백 (CTR 높을수록 winner 확률 ↑ → 양의 상관)
    n_fb = 0
    targets = [rng.choice(variant_pool) for _ in range(60)]
    for gid in targets:
        meta = job_store.get_variant_meta(gid)
        if not meta:
            continue
        ctr = meta["ctr_estimate"]
        # CTR 기반 winner 확률
        p_winner = min(0.9, max(0.1, (ctr - 40) / 60))
        roll = rng.random()
        if roll < p_winner:
            ftype = "winner"
        elif roll < p_winner + 0.3:
            ftype = "loser"
        else:
            ftype = "discard"
        feedback_store.record_feedback(FeedbackEntry(
            feedback_type=ftype, user_note="[seed]", **meta))
        n_fb += 1

    print(f"시드 완료: generation 메타 20건, variant {len(variant_pool)}개, 피드백 {n_fb}건")
    print("→ 서버를 켜고 '성과 분석' 탭에서 확인하세요. 제거: python scripts/seed_feedback.py --reset")


def main() -> None:
    ap = argparse.ArgumentParser(description="피드백 시드 데이터")
    ap.add_argument("--reset", action="store_true", help="시드 데이터만 삭제(실제 데이터 보존)")
    args = ap.parse_args()
    if args.reset:
        _reset()
    else:
        _seed()


if __name__ == "__main__":
    main()
