# 다음 작업: 라이프스타일 생성 시스템 (A+B 통합)

> 작성: 2026-05-27
> 상태: 시작 대기 (다른 PC에서 이어서 진행 예정)
> 작업 브랜치: feature/lifestyle-generation

## 배경 — 사용자 불만 사항

현재 결과물 수준이 너무 떨어짐. 사용자가 요구한 카카오톡 이미지 수준
(라이프스타일 신, 벽지·바닥·소품·조명 포함)이 안 나오고 있음.

원인:
1. 제품 정보 입력칸이 아예 없음 (사이즈, 재질, 카테고리, 색상 등)
2. mock 그라데이션 배경이 전부 (실제 AI 이미지 생성 안 함)
3. 카테고리별 배치 로직 없음 (가구든 옷이든 같은 자리에 박힘)

## 목표

사용자가 가구/의류/식품 등 카테고리 선택 + 제품 정보 입력하면,
실제 AI 이미지 생성으로 라이프스타일 신 만들고 카테고리에 맞게
제품 배치까지 자연스럽게 처리.

## 사전 준비 (다른 PC에서 시작 전 확인)

- [ ] git clone 후 setup.bat 실행 완료
- [ ] .env에 STABILITY_API_KEY 추가 (없으면 OPENAI_API_KEY로 DALL-E 폴백)
- [ ] Stability AI 결제 등록 (이미지 1장당 약 25원)
- [ ] git config 본인 이름/이메일 설정 완료

## Claude Code에 그대로 붙여넣을 명령

아래 코드 블록 전체를 Claude Code에 복사해서 보내면 11단계 자동 진행.

```
A + B 작업을 한 번에 진행한다. 절대 작업 중간에 멈추거나 사용자에게 묻지 마라.
모든 결정은 아래 명세에 따라라. Bypass 모드이므로 자동 진행.

【배경 — 사용자 불만 사항】
현재 결과물 수준이 너무 떨어짐. 사용자가 요구한 카카오톡 이미지 수준
(라이프스타일 신, 벽지·바닥·소품·조명 포함)이 안 나오고 있음.
원인:
1. 제품 정보 입력칸이 아예 없음 (사이즈, 재질, 카테고리, 색상 등)
2. mock 그라데이션 배경이 전부 (실제 AI 이미지 생성 안 함)
3. 카테고리별 배치 로직 없음 (가구든 옷이든 같은 자리에 박힘)

【목표】
사용자가 가구/의류/식품 등 카테고리 선택 + 제품 정보 입력하면,
실제 AI 이미지 생성으로 라이프스타일 신 만들고 카테고리에 맞게
제품 배치까지 자연스럽게 처리.

【작업 브랜치】 feature/lifestyle-generation

═══════════════════════════════════════
【1단계: 환경 점검】
═══════════════════════════════════════
1-1. git status (clean), git log --oneline -3
1-2. .env의 키 형식만 검증 (값 출력 금지):
     - STABILITY_API_KEY 있는가?
     - 없으면 OPENAI_API_KEY로 DALL-E 폴백 가능한가?
     - 둘 다 없으면 멈추고 사용자에게 한 번만 안내 후 대기

═══════════════════════════════════════
【2단계: 제품 정보 입력 시스템】
═══════════════════════════════════════
2-1. app/models/schemas.py에 ProductInfo 추가:
     class ProductInfo:
       product_name: str | None
       brand_name: str | None
       category: str  # 가구/의류/식품/전자제품/뷰티/생활용품/액세서리/기타
       sub_category: str | None
       size_w: float | None  # 가로 cm
       size_h: float | None
       size_d: float | None
       size_label: str | None  # S/M/L
       material: str | None
       color: str | None
       use_space: str | None  # 거실/침실/주방/욕실/사무실/야외/공용
       target_audience: str | None
       mood_keywords: list[str] | None  # ["미니멀", "북유럽"]

2-2. GenerateRequest에 product_info 필드 추가 (Optional)

2-3. config/categories_v2.yaml 신규:
     - 8개 메인 카테고리 + 각 sub_category 리스트
     - 카테고리별 권장 mood_keywords
     - 카테고리별 적합한 use_space

2-4. 프론트엔드 단일 생성 탭 좌측에 "2. 제품 정보" 섹션 추가:
     - 카테고리 select (필수)
     - sub_category select (동적)
     - 제품명, 브랜드명 input
     - 사이즈: 가로/세로/깊이 또는 S/M/L 토글
     - 재질, 색상 input
     - 사용 공간 select
     - 타겟 input
     - 무드 키워드 multi-select chip
     기존 "2. 옵션"은 "3. 옵션"으로 번호 변경

═══════════════════════════════════════
【3단계: 실제 AI 이미지 생성 깊이 구현】
═══════════════════════════════════════
3-1. app/providers/stability_provider.py 실제 구현:
     - SDXL 1024×1024, cfg_scale 7, steps 30
     - 응답 base64 → PIL Image
     - 에러 시 DALL-E 폴백, 둘 다 실패 시 mock 폴백

3-2. app/providers/openai_provider.py에 dall-e-3 호출 추가:
     - 1024×1024 standard
     - 에러 시 mock 폴백

3-3. app/core/scene_prompt.py 신규 — 프롬프트 자동 생성기:

     def build_scene_prompt(product_info, concept, platform) -> (positive, negative)

     카테고리별 기본 신:
     - 가구 → "spacious minimal {use_space} interior, {color} walls, wooden flooring, soft natural daylight, {mood} atmosphere"
     - 의류 → "minimal clothing rack in {use_space}, white walls with line art posters, wooden floor, soft natural lighting, scandinavian style"
     - 식품 → "clean kitchen counter, marble surface, soft window light, minimal styling"
     - 전자제품 → "minimal modern desk setup, white wall, soft directional lighting"
     - 뷰티 → "clean cosmetics shelf, marble background, soft pink/beige tones, delicate flowers"
     - 액세서리 → "minimal display surface, neutral fabric, premium showcase"
     - 생활용품 → "minimal home setting, soft natural lighting"

     컨셉별 모드 키워드 (18개 컨셉 매핑):
     - premium_luxury → "luxury, elegant, sophisticated lighting"
     - white_minimal → "minimalist, clean, lots of whitespace"
     - coupang_sales → "bright commercial, vibrant"
     ...

     제품 정보 반영:
     - material → 배경 톤·재질감
     - color → 배경 보색/조화색
     - mood_keywords → 직접 주입

     Negative prompt:
     "product, item, foreground subject, watermark, text, logo,
      multiple objects, blurry, low quality, distorted"

3-4. 프롬프트 캐싱:
     - (product_info hash, concept, platform) 키로 24시간 캐시
     - workspace/temp/scene_cache.json
     - fresh=true 옵션으로 강제 새로 생성

═══════════════════════════════════════
【4단계: 카테고리별 제품 배치 로직】
═══════════════════════════════════════
4-1. app/core/placement.py 신규:
     get_placement_rules(category, sub_category) -> PlacementRule

     - 가구 → 바닥 자연 배치, 그림자 강하게, 원근감
       소파/의자/테이블: 하단 중앙 60-70%
       책장/옷장: 중앙 80%
     - 의류 → 행거에 걸린 듯, 그림자 약하게
       상의/원피스: 중앙 상단 70%
       신발: 하단 40%
     - 식품 → 식탁 위, 그림자 짧게
     - 전자제품 → 데스크 위, 그림자 선명
     - 뷰티 → 진열대, 그림자 부드럽게
     - 액세서리 → 클로즈업, 그림자 디테일

4-2. composer.py 수정:
     - fit_product_to_box를 카테고리별 placement로 교체
     - 그림자 강도/방향/길이 카테고리별 다르게
     - harmonize_with_background: 채도/명도 ±5% 보정

═══════════════════════════════════════
【5단계: 레퍼런스 이미지 업로드】
═══════════════════════════════════════
5-1. POST /api/reference/upload 신규:
     - 자동 분석: dominant 컬러 3개, 톤, 무드 키워드 추출
     - 다음 generate 호출에 자동 반영

5-2. 단일 생성 탭에 "레퍼런스 이미지 (선택)" 영역:
     - 작은 드롭존
     - 추출된 색/무드 chip 표시
     - X 버튼

5-3. 분석 결과를 scene_prompt 추가 컨텍스트로 주입

═══════════════════════════════════════
【6단계: 1장씩 생성으로 변경】
═══════════════════════════════════════
6-1. GenerateRequest.variants 기본값 4 → 1
6-2. 프론트엔드 "생성 개수" 기본 1 (max 4 유지)
6-3. "더 만들기" 버튼: 같은 prompt로 1장 더 (다른 시드)
6-4. 비용 표시: "예상 비용: ~25원" (Stability: 25원, DALL-E: 50원)

═══════════════════════════════════════
【7단계: 자체 검수 강화】
═══════════════════════════════════════
7-1. qc.py 추가 검수:
     - 배경에 제품 닮은 객체 검출
     - 텍스트 깨짐 검출
     - 제품이 배경에 묻혔는지 대비 검사
     - 카테고리 위반 (가구에 사람, 의류에 마네킹 등)

7-2. QC 실패 시 1회 재생성 (시드 다르게), 그래도 실패 시 정직 표시

═══════════════════════════════════════
【8단계: 테스트】
═══════════════════════════════════════
8-1. tests/test_scene_prompt.py: 144개 조합 검증 (실호출 X)
8-2. tests/test_placement.py: 카테고리별 규칙
8-3. tests/test_product_info.py: ProductInfo 검증
8-4. RUN_LIVE_IMAGE_TEST=true일 때만 Stability+DALL-E 각 1회 실호출
8-5. 기존 91개 테스트 그대로 통과

═══════════════════════════════════════
【9단계: 자체 검수 (보고 전)】
═══════════════════════════════════════
9-1. 모든 테스트 통과
9-2. uvicorn 서버 띄우고 엔드포인트 응답 확인
9-3. 새 UI 필드 동작 확인
9-4. 캐시 폴더 권한
9-5. .env 키 누락 폴백 검증
9-6. 모두 통과 → 10단계

═══════════════════════════════════════
【10단계: 실제 이미지 1장 생성】
═══════════════════════════════════════
10-1. 자동 검증 케이스:
      - 가짜 책상 PNG 생성
      - ProductInfo: 가구/책상/120x60x75/원목/화이트/서재/[미니멀,북유럽]
      - 컨셉: white_minimal, 플랫폼: coupang, variants=1
      - Stability(없으면 DALL-E) 호출
      - workspace/outputs/_qa_sample/sample.png 저장

10-2. 결과 보고: 파일/QC 점수/사용 프롬프트/비용

10-3. 사용자에게 안내: "workspace/outputs/_qa_sample/sample.png 확인 부탁"

═══════════════════════════════════════
【11단계: 커밋 + 머지 + push】
═══════════════════════════════════════
11-1. 단계별 작은 커밋 8개
11-2. feature/lifestyle-generation → main (--no-ff)
11-3. origin push

═══════════════════════════════════════
【규칙】
═══════════════════════════════════════
- 작업 중 사용자에게 묻지 마라
- 실호출은 10단계 1회만
- 다른 provider 추가 금지 (Stability + OpenAI만)
- selenium/playwright 금지
- 한글 주석/UI 유지
- 기존 91개 통과 안 하면 머지 금지
- _qa_sample/, scene_cache.json 등 .gitignore 추가
- 레퍼런스 이미지 외부 전송 X

【최종 보고】
- 환경 / 신규파일 / 테스트 통과 X/Y / 자체검수 / 실생성 1장 결과
- 사용 provider, 비용, 파일 경로, QC 점수, 사용된 프롬프트
- Git 브랜치/머지/push
- 미해결 이슈 / 다음 추천

1단계부터 시작. 끝까지 진행. 멈추지 마라.
```

## 진행 후 결과 기록

(다른 PC에서 작업 완료 시 여기에 결과 요약 적기)