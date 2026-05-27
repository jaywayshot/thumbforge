# 🎨 ThumbForge — AI 쇼핑몰 썸네일 생성 SaaS (MVP)

> 제품 이미지 → AI 자동 누끼 → 컨셉 배경 → **매출형 썸네일 N장** 자동 생성

**핵심 원칙**

1. ✅ **제품 원본 훼손 금지** — AI가 제품을 다시 그리지 않고, 누끼된 원본을 그대로 사용
2. ✅ **하드코딩 금지** — 컨셉/플랫폼/카테고리 모두 YAML 분리
3. ✅ **AI Provider 교체 가능** — `mock` / `openai` / `stability` / `gemini`
4. ✅ **플랫폼별 정책 분리** — 쿠팡/스마트스토어/아마존 등 금지문구/사이즈
5. ✅ **API 키 없이 즉시 실행** — mock 모드로 그라데이션·조명 효과로 배경 합성

---

## ⚡ 빠르게 시작 (3분)

### 윈도우

터미널(cmd 또는 PowerShell)에서 프로젝트 폴더로 이동 후:

```bat
setup.bat
run.bat
```

`setup.bat` 한 번만 실행하면 가상환경 + 의존성 + `.env`까지 자동 셋업됩니다.
`run.bat` 실행 시 서버가 켜지고 **브라우저가 자동으로 열립니다**: <http://127.0.0.1:8000>

### macOS / Linux

```bash
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

### 첫 실행 시 주의
- **누끼 모델(rembg)** 이 약 170MB 다운로드됩니다. 첫 생성에 1~2분 걸릴 수 있습니다.
- 두 번째 생성부터는 수 초.

---

## 🖱️ 사용법 (브라우저 GUI)

1. 좌측 **드래그앤드롭** 박스에 제품 이미지(PNG/JPG/WEBP) 올리기
2. 컨셉(쿠팡 판매형 · 스마트스토어 감성형 · 프리미엄 럭셔리 등) + 플랫폼 선택
3. 생성 개수(기본 4), 할인%, 헤드라인/서브/뱃지 입력 (비우면 AI 자동 추천)
4. **썸네일 생성하기** 클릭 → A/B 테스트용 N장 자동 생성
5. **CTR 점수 순으로 정렬** + 각각 다운로드

---

## 🚀 v2 추가 기능

### 📦 대량(Bulk) 처리

브라우저 상단 **대량 처리** 탭 → ZIP 파일 업로드 → 각 이미지별 N개 variant 자동 생성 → 결과 ZIP 다운로드.

- 진행률 실시간 polling
- 결과 ZIP 안에 제품별 폴더로 정리
- `_summary.json`에 각 결과의 CTR 점수/QC 노트 모두 포함

API로도 호출 가능:
```bash
# 업로드 (즉시 job_id 반환)
curl -X POST http://127.0.0.1:8000/api/bulk/upload \
  -F "file=@products.zip" \
  -F "concept=white_minimal" \
  -F "platform=coupang" \
  -F "variants_per_image=3"

# 상태 조회
curl http://127.0.0.1:8000/api/bulk/status/<job_id>

# 결과 ZIP 다운로드
curl -O http://127.0.0.1:8000/api/bulk/result/<job_id>.zip
```

### 🎨 브랜드 관리

브라우저 **브랜드 관리** 탭 → `+ 새 브랜드` → 브랜드 컬러/로고/폰트/기본 문구 저장.

저장된 브랜드는 단일/대량 생성 시 **브랜드 드롭다운**에 자동으로 노출됩니다. 선택하면:
- 컨셉의 `accent_color`/`sub_color`/`text_color`를 브랜드 컬러로 덮어쓰기
- 모든 텍스트에 브랜드 폰트 우선 적용
- 우상단에 로고 자동 워터마크
- 브랜드 금지문구 추가 검사

### 🎯 검수 강화

CTR 점수가 단순 대비/밝기를 넘어 다음 4개 요소의 가중합:
- 색 대비 (전체 표준편차)
- 시선 집중도 (중앙 vs 외곽 차이)
- 색 다양성 (양자화 후 고유 색 수)
- QC 가독성 점수 + 할인/뱃지 보너스

---

## 🔍 경쟁사 분석 (현재 상태: 수집 차단 — 보류)

브라우저 **경쟁사 분석** 탭 또는 `POST /api/analyze/competitor` 로 검색결과 URL을 넣으면,
상위 상품 썸네일의 dominant 컬러·배경 톤·할인 뱃지 비율을 분석해 적합한 컨셉을 추천합니다.
URL 도메인으로 **쿠팡 / 11번가 / 네이버 쇼핑**을 자동 감지하는 어댑터 구조입니다
(`app/analyzers/sites.py`). 결과는 URL 해시 키로 24시간 캐시됩니다.

> **원칙**: robots.txt 존중 · 정직한 User-Agent · 정적 HTML만 파싱 ·
> 헤드리스 브라우저/IP 우회/UA 위장 **사용하지 않음**.

### 사이트별 수집 가능 여부 (2026-05 확인)

| 사이트 | robots.txt | 정적 HTML | 상태 |
|---|---|---|---|
| 쿠팡 | 403 (Akamai가 robots.txt까지 차단) | 403 Forbidden | ❌ 봇 차단 |
| 네이버 쇼핑 | `Disallow: /` (ClaudeBot 포함 전면 금지) | 418 | ❌ robots 금지 → 시도 안 함 |
| 11번가 | ✅ 허용(`Allow: /Search*`) | 상품이 JS(SPA)로 렌더 → 정적 HTML에 상품 이미지 0개 | ⚠ 정적 수집 불가 |

세 사이트 모두 **허용된 방법(정적 HTML)으로는 실데이터를 얻을 수 없어 현재 보류** 상태입니다.
코드/어댑터/추천 로직은 그대로 유지되며, **어느 사이트가 정적 HTML을 제공하면 셀렉터만으로 즉시 동작**합니다.
로직 정확성은 모킹 HTML 기반 단위 테스트(`tests/test_competitor.py`)로 검증됩니다.

### 실데이터가 필요할 때 — 쿠팡 파트너스 OPEN API (권장 경로)

스크래핑 대신 **공식 제휴 API**를 사용하세요. 약관을 준수하며 차단 없이 상품 데이터를 받습니다.

1. 쿠팡 파트너스 가입: <https://partners.coupang.com> → 회원가입/사업자 인증
2. 승인 후 **액세스 키 / 시크릿 키** 발급 (마이페이지 → OPEN API)
3. 상품 검색 API: `GET /v2/providers/affiliate_open_api/apis/openapi/v1/products/search`
   (HMAC 서명 헤더 `Authorization: CEA algorithm=..., signature=...` 필요)
4. 발급받은 키를 `.env`에 추가 후, `app/analyzers/sites.py`에 파트너스-API 어댑터를 추가하면
   기존 분석 파이프라인을 그대로 재사용할 수 있습니다.

> 네이버는 쇼핑 검색 스크래핑을 robots.txt로 금지하므로, 네이버 쇼핑 데이터가 필요하면
> **네이버 검색 OPEN API / 쇼핑파트너센터** 등 공식 채널을 사용해야 합니다.

---



### 1) 업로드

```bash
curl -X POST http://127.0.0.1:8000/api/upload \
  -F "file=@my_product.png"
```

응답:
```json
{
  "upload_id": "a1b2c3d4e5f6",
  "filename": "my_product.png",
  "width": 1200, "height": 1200,
  "has_alpha": false,
  "detected_category": "electronics",
  "suggested_concepts": ["tech_electronics", "apple_style", "black_luxury"],
  "quality_warnings": []
}
```

### 2) 생성

```bash
curl -X POST http://127.0.0.1:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "a1b2c3d4e5f6",
    "concept": "coupang_sales",
    "platform": "coupang",
    "variants": 4,
    "text": {
      "headline": "오늘의 베스트",
      "sub_text": "무료배송 · 당일출고",
      "badge": "BEST",
      "discount_percent": 30
    }
  }'
```

### 3) 컨셉/플랫폼 목록

```bash
curl http://127.0.0.1:8000/api/concepts
curl http://127.0.0.1:8000/api/platforms
```

---

## 💻 CLI 배치 생성 (서버 없이)

브라우저/서버 없이 터미널에서 폴더를 일괄 처리합니다. (내부적으로 동일 파이프라인 사용)

```bash
# 폴더 일괄 처리
python scripts/generate_cli.py --input ./in --concept white_minimal \
    --platform coupang --variants 4 --output ./out

# 단일 이미지
python scripts/generate_cli.py -i product.png -o ./out -c apple_style -n 2
```

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `-i, --input` | 이미지 파일 또는 폴더 (필수) | — |
| `-o, --output` | 결과 폴더 | `./workspace/cli_out` |
| `-c, --concept` | 컨셉 이름 | `white_minimal` |
| `-p, --platform` | 플랫폼 이름 | `coupang` |
| `-n, --variants` | 이미지당 생성 개수 | `4` |
| `--category` | 카테고리 힌트(선택) | 파일명 자동 추정 |
| `--headline` | 헤드라인(비우면 자동 추천) | — |

결과 파일명은 `<원본이름>_v1.png`, `<원본이름>_v2.png` … 형식입니다.

---

## 🔁 AI Provider 교체

`.env` 파일을 열고:

```env
# mock (기본) | openai | stability | gemini
BG_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

- 키가 비어있거나 호출 실패 시 **자동으로 mock 폴백** → 절대 에러 안 남
- 새로운 Provider 추가는 `app/providers/` 에 어댑터 클래스 하나 만들고 `factory.py` 에 한 줄 추가하면 끝

추가 패키지가 필요할 수 있습니다:
```bash
.venv\Scripts\activate.bat    # Windows
source .venv/bin/activate     # mac/Linux
pip install openai            # OpenAI 쓸 때
pip install google-generativeai   # Gemini 쓸 때
```

---

## 🧠 LLM 문구 추천 (OpenAI / Anthropic)

업로드한 제품의 **카테고리 + 컨셉 + 플랫폼**에 맞는 매출형 문구(헤드라인/서브/뱃지)를
실제 LLM 으로 생성합니다. 키가 없으면 자동으로 mock 폴백되어 **에러 없이** 동작합니다.

### 환경변수

```env
# 문구 provider 선택: mock(기본) | openai | anthropic
TEXT_PROVIDER=openai

# OpenAI (기본 모델 gpt-4o-mini)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini        # 선택, 미설정 시 gpt-4o-mini

# Anthropic (기본 모델 claude-haiku-4-5)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5  # 선택
```

> 한 호출당 응답 토큰은 **max_tokens=300** 으로 고정(비용 폭주 방지).
> 추가 패키지: `pip install openai` 또는 `pip install anthropic` (선택적 의존성).

### 검증 레이어 (두 provider 공통 — `app/providers/llm_support.py`)

- 출력은 JSON 강제(`{headline, sub_text, badge}`), 18개 컨셉별 **톤 가이드** + 플랫폼 **금지어**를 system 프롬프트에 주입
- **JSON 파싱 실패** → mock 폴백
- **필드 누락** → 누락 필드만 mock 으로 채움
- **글자수 초과**(헤드라인 12 / 서브 16 / 뱃지 6자) → 잘라내기 + 경고 로깅
- **금지어 포함** → 1회 재호출(regenerate), 그래도 포함이면 mock 폴백

### 캐싱

- 키: `(provider, model, category, concept, platform)` 해시
- 파일: `workspace/temp/llm_cache.json`, **TTL 24시간**, **1MB 초과 시 오래된 항목부터 자동 삭제**
- `/api/text/suggest` 요청에 `fresh=true` 를 주면 캐시를 무시하고 새로 생성

### 사용량 추적

- 호출마다 토큰 수·예상 비용을 로깅하고 `workspace/temp/llm_usage.jsonl` 에 한 줄씩 기록
- 누적 통계: `GET /api/llm/usage` (총 호출/토큰/비용, 모델별 분해)

### API / UI

```bash
curl -X POST http://127.0.0.1:8000/api/text/suggest \
  -H "Content-Type: application/json" \
  -d '{"category":"electronics","concept":"tech_electronics","platform":"coupang"}'

curl http://127.0.0.1:8000/api/llm/usage
```

브라우저 **단일 생성** 탭의 `✨ LLM 문구 생성` 버튼을 누르면 현재 카테고리/컨셉/플랫폼으로
호출해 입력칸을 자동으로 채웁니다.

### 품질 평가 도구 (수동 실행)

8개 컨셉 × 4개 카테고리 = 32개 조합을 호출해 글자수 초과·금지어·카테고리 적합도를 표로 정리합니다.
**캐시를 무시하고 호출**하며(정확한 측정), 결과는 `workspace/temp/llm_eval.md` 에 저장됩니다.

```bash
python scripts/eval_llm_quality.py --provider openai   # 실호출 → 비용 발생(실행 전 확인)
python scripts/eval_llm_quality.py --provider mock     # 무료(로직 점검)
```

> ⚠ 실 provider 로 실행하면 32회 실호출 → 비용이 발생합니다. 스크립트가 실행 전 확인을 받습니다(`--yes` 로 생략).

---

## 👍 피드백 시스템 (variant 선호 데이터 축적)

생성된 4~6개 variant 중 사용자가 "좋다/별로다/안 쓴다"를 표시하면, 그 데이터를 쌓아
어떤 **컨셉·레이아웃·문구 패턴**이 선호되는지 분석합니다. 데이터는 **외부로 전송하지 않고**
`workspace/feedback/` 에만 저장됩니다.

### 사용법 (브라우저)

- **단일 생성** 결과 카드의 `👍 / 👎 / ✕` 버튼 → 즉시 기록(토스트 "기록됨")
  - 같은 카드에서 다른 버튼을 누르면 덮어쓰기(마지막 의견이 진실)
- **성과 분석** 탭 → 컨셉별/레이아웃별/provider별 winner rate(CSS 막대그래프),
  할인 뱃지 유무 비교, CTR 추정 ↔ 선택 상관(피어슨), 상단 요약, CSV 다운로드

### 저장 방식

- `workspace/feedback/feedback.jsonl` 에 한 줄 = 한 피드백 (**append-only**)
- **1MB 초과 시 회전**: `feedback.jsonl` → `feedback-001.jsonl` (rename, 원자적) 후 새 파일
- 같은 variant 의 의견 변경은 새 줄로 추가되고, 조회 시 **가장 최근 항목만** 유효(무손실 + 덮어쓰기)
- generation 메타데이터는 `workspace/jobs/<job_id>.json` 에 저장되어 피드백 시 자동 복원

### API

```bash
curl -X POST http://127.0.0.1:8000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"variant_id":"<job_id>_v1","feedback_type":"winner"}'   # winner|loser|discard

curl http://127.0.0.1:8000/api/feedback/recent?limit=50
curl http://127.0.0.1:8000/api/feedback/stats
curl -O http://127.0.0.1:8000/api/feedback/export.csv
```

### 도구 (수동 실행)

```bash
python scripts/seed_feedback.py          # 가짜 피드백 60건 생성(통계 화면 확인용)
python scripts/seed_feedback.py --reset  # 시드 데이터만 삭제(실제 데이터 보존)
python scripts/cleanup_old_jobs.py --days 30   # 30일 지난 generation 메타 정리
```

---

## 🎨 컨셉 추가/수정 (하드코딩 0)

`config/concepts.yaml` 만 편집하면 새 컨셉이 즉시 UI에 노출됩니다.

```yaml
my_brand_dark:
  label: "내 브랜드 다크형"
  description: "..."
  background:
    type: gradient            # gradient | solid | diagonal_split
    colors: ["#000000", "#222222"]
    angle: 135
  accent_color: "#FFD700"
  sub_color: "#FFFFFF"
  text_color: "#FFFFFF"
  layout: center_product       # left_product_right_text | center_product
                               # center_product_top_text | huge_text_top
                               # huge_center_product | diagonal
  badge_style: gold_serif
  headline_max: 10
  prompt_keywords: "luxury dark, gold accent"   # AI Provider 사용시
```

플랫폼 정책도 동일: `config/platforms.yaml`
카테고리 매핑도 동일: `config/categories.yaml`

---

## ⚙️ Celery + Redis 전환 방법

기본값은 **단일 프로세스 스레드풀**입니다. 별도 설치 없이 대량 처리가 그대로 동작합니다.
트래픽이 늘어 워커를 분리하고 싶을 때만 아래처럼 Celery로 전환합니다. **코드 변경은 필요 없습니다.**

### 동작 방식
- 대량 처리 디스패치는 `app/jobs/celery_app.py` 의 `dispatch_bulk_job()` 한 곳을 거칩니다.
- `USE_CELERY=true` + `celery` 설치 + Redis 가동 → **Celery 큐**로 처리
- 그 외(기본) → 기존 **스레드풀**(`registry.run_in_background`)로 처리
- 작업 진행률 추적용 `app/jobs/registry.py` 인터페이스는 **그대로** 유지됩니다.

### 전환 절차

1. Redis + 워커 컨테이너 기동 (정의는 `docker-compose.yml` 에 있음):

   ```bash
   docker compose up -d redis worker
   ```

   > 워커 컨테이너는 기동 시 `requirements.txt` + `celery[redis]` 를 설치하고
   > `celery -A app.jobs.celery_app:celery_app worker` 를 실행합니다.

2. 앱(FastAPI)을 Celery 모드로 실행 — 환경변수만 추가:

   ```bash
   # .env 에 추가하거나 실행 시 주입
   USE_CELERY=true
   REDIS_URL=redis://localhost:6379/0
   ```

   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

3. 로컬에서 Docker 없이 직접 워커를 띄우려면:

   ```bash
   pip install "celery[redis]"
   celery -A app.jobs.celery_app:celery_app worker --loglevel=info
   ```

### 되돌리기
`USE_CELERY` 를 지우거나 `false` 로 두면 즉시 스레드풀 모드로 복귀합니다.
`celery` 패키지가 없어도 앱 import/실행은 깨지지 않습니다(선택적 의존성).

---

## 📁 폴더 구조

```
THUMBNAIL_SAAS/
├── config/                  # YAML 설정 (하드코딩 분리)
│   ├── concepts.yaml        # 17가지 컨셉 프리셋
│   ├── platforms.yaml       # 쿠팡/스마트스토어/아마존 등 정책
│   └── categories.yaml      # 카테고리 → 추천 컨셉
├── app/
│   ├── main.py              # FastAPI 진입점
│   ├── settings.py          # .env 로딩
│   ├── api/                 # REST 라우트
│   │   ├── routes_upload.py
│   │   ├── routes_generate.py
│   │   ├── routes_bulk.py   # 대량 ZIP 처리 (v2)
│   │   ├── routes_brand.py  # 브랜드 CRUD (v2)
│   │   └── routes_download.py
│   ├── core/                # 핵심 로직
│   │   ├── matting.py       # 누끼 (rembg + 폴백)
│   │   ├── composer.py      # 배경+제품+텍스트+로고 합성
│   │   ├── text_overlay.py  # 한글 폰트/뱃지/할인 폭발/브랜드 폰트
│   │   ├── layout.py        # 6종 레이아웃
│   │   ├── qc.py            # 검수 + CTR 추정 (saliency 포함, v2)
│   │   └── pipeline.py      # 메인 파이프라인 (브랜드 적용 포함, v2)
│   ├── jobs/                # 백그라운드 작업 (v2)
│   │   ├── registry.py      # 인메모리 job 추적 (→ Celery 교체 가능)
│   │   ├── bulk_worker.py   # ZIP 일괄 처리 워커
│   │   └── celery_app.py    # Celery 인스턴스 + 디스패처 (USE_CELERY 시)
│   ├── providers/           # AI Provider (어댑터 패턴)
│   │   ├── base.py
│   │   ├── mock.py          # ★기본
│   │   ├── openai_provider.py
│   │   ├── stability_provider.py
│   │   ├── gemini_provider.py
│   │   └── factory.py
│   ├── models/schemas.py    # Pydantic I/O
│   ├── services/            # 로더 / 저장소
│   │   ├── concept_loader.py
│   │   ├── storage.py
│   │   └── brand_store.py   # 브랜드 JSON 영속화 (v2)
│   └── static/index.html    # 데모 UI (3탭: 단일/대량/브랜드)
├── workspace/               # 자동 생성
│   ├── uploads/             # 업로드 원본
│   ├── outputs/<job_id>/    # 단일 결과물
│   ├── outputs/bulk/        # 대량 결과 ZIP
│   ├── brands/<id>/         # 브랜드 로고/폰트
│   ├── brands.json          # 브랜드 메타 영속화
│   └── temp/
├── assets/fonts/            # (선택) 한글 폰트 직접 넣기
├── .env.example
├── requirements.txt
├── setup.bat / setup.sh
└── run.bat / run.sh
```

---

## 🔧 한글 폰트가 안 보일 때

Windows / macOS는 시스템 한글 폰트를 자동 탐지합니다.
Linux 서버 또는 컨테이너에서 안 보이면:

```bash
# Ubuntu
sudo apt install fonts-nanum
```

또는 프로젝트의 `assets/fonts/` 폴더에 `.ttf`/`.otf` 파일을 넣으면
다른 폰트보다 **최우선으로** 사용됩니다.

---

## 🛣️ 로드맵 (기획서 매핑)

| 단계 | 항목 | 상태 |
|---|---|---|
| MVP | 업로드 → 누끼 → 컨셉 배경 → 합성 → 문구 → N장 생성 → 다운로드 | ✅ |
| MVP | CTR 추정 점수 / 플랫폼별 정책 검수 (saliency + 색 다양성) | ✅ |
| MVP | Provider 교체 가능 구조 (mock/openai/stability/gemini) | ✅ |
| v2 | **대량 ZIP 업로드 → 일괄 처리 → 결과 ZIP** (인메모리 job queue) | ✅ |
| v2 | **브랜드 관리** (로고/컬러/폰트/기본문구/금지어) | ✅ |
| v2 | **CTR 점수 강화** (시선 집중도 + 색 다양성) | ✅ |
| 다음 | 실제 LLM 문구 추천 (OpenAI/Anthropic 깊이 구현) | ✅ 검증레이어(누락/길이/금지어 재호출)·캐시(24h,1MB)·사용량(/api/llm/usage)·평가도구. 키 없으면 mock 폴백 (상단 "LLM 문구 추천" 절) |
| 다음 | variant 피드백 수집 + 성과 분석 (winner/loser, 컨셉·레이아웃·provider별 통계) | ✅ append-only jsonl(1MB 회전)·CSV export·성과분석 탭 (상단 "피드백 시스템" 절) |
| 다음 | Celery + Redis 전환 (USE_CELERY 플래그 + docker-compose, 기본은 스레드풀) | ✅ 전환 준비 |
| 다음 | 경쟁사 URL 분석 (쿠팡/11번가/네이버 어댑터, 색감/뱃지 패턴 → 컨셉 추천) | ⚠️ 구현 완료·**실수집 보류**: 3사 모두 정적 HTML 차단(상단 "경쟁사 분석" 절 참고). 공식 API 경로 안내. 모킹 로직 검증 유지 |
| 다음 | 회원/요금제/크레딧/팀/API 키 | 🔜 |
| 확장 | 유튜브 썸네일 / 쇼츠·릴스 / 광고 소재 / 상세페이지 자동 생성 | 🔜 |

---

## 🧪 트러블슈팅

| 증상 | 해결 |
|---|---|
| `numpy`/빌드 실패 (Python 3.13+) | 3.13/3.14는 옛 핀 버전 휠이 없어 빌드로 떨어짐. `pip install -r requirements-py314.txt` 사용 (setup 스크립트는 자동 선택) |
| `rembg` 설치 실패 | `pip install --upgrade pip setuptools wheel` 후 재시도 |
| 첫 생성이 느림 | rembg 모델 다운로드. 2회차부터 빨라짐 |
| 한글이 ⬜로 보임 | 위의 "한글 폰트가 안 보일 때" 참고 |
| 포트 8000 사용중 | `.env` 의 `PORT=8001` 로 변경 |
| 윈도우에서 한글 깨짐 | cmd가 아니라 Windows Terminal / PowerShell 사용 |

---

## 📝 라이선스

MVP 자체 코드는 자유 수정/사용. 의존 패키지(rembg/Pillow/FastAPI 등)는 각자 라이선스 준수.
