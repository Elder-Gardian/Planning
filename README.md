# Elder Guardian Planning

노인 복지 사각지대 분석과 신규 경로당 입지 추천 방법론을 설명하는 **GitHub Pages용 정적 보고서 사이트**입니다. 실행형 모델이나 API 서버가 아니라, WelfareMap AI의 사업 정의·기술 설계·이중 그래프 구조·근거와 검증 기준을 웹 문서로 제공합니다.

정적 배포물은 `site/`에 있으며 별도 애플리케이션 런타임 없이 브라우저에서 열 수 있습니다.

## 문서 구성

사이트는 네 문서로 구성됩니다.

| 페이지 | 내용 | 원문·근거 |
|---|---|---|
| `site/index.html` | 방법론 종합 보고서와 P0 의사결정 계약 | `sources/methodology-notes.md`의 근거 노트를 바탕으로 별도 관리 |
| `site/planning.html` | WelfareMap AI 사업 기획서 | `content/planning.md`에서 생성 |
| `site/technical-blueprint.html` | 데이터·모델·solver·검증 기술 청사진 | `content/technical-blueprint.md`에서 생성 |
| `site/dual-graph-recommendation.html` | 100m 물리 격자와 상태 확장 경로 그래프 설계 | `content/dual-graph-recommendation.md`에서 생성 |

`scripts/build-document-pages.mjs`는 `content/`의 Markdown 세 문서를 대응하는 HTML로 변환합니다. `site/index.html`은 이 스크립트가 다시 생성하지 않습니다. 공통 스타일과 상호작용은 `site/report.css`, `site/report.js`가 담당하며, `site/.nojekyll`과 함께 `site/` 전체가 배포 대상입니다.

생성된 HTML도 저장소에서 관리하므로 원문을 변경했다면 대응하는 HTML을 함께 다시 생성해야 합니다. 생성물을 직접 수정하면 다음 빌드에서 덮어써질 수 있습니다.

## P0 확정 설계

P0는 대상 자치구에 **신규 경로당 1개**를 배치하는 입지 추천 문제입니다.

- 수요는 100m 격자·시간대별 **예상 동시 이용자 수**이며, 에이전트가 변경할 수 없습니다.
- 기존 공급은 경로당·노인복지관 등 **시설 유형별 동시수용량**으로 분리합니다.
- 행동은 `FEASIBLE` 후보 격자 한 곳을 고르는 **위치-only action**입니다.
- 신설 면적과 용량은 총예산, 토지비, 공사비, 건폐율·용적률과 법적 최소기준을 적용한 필지 solver가 산출합니다.
- 수요와 신규 후보는 대상 자치구로 제한하지만, 이동 경로는 **수도권 전체 교통망**에서 탐색하여 경계 밖 환승과 우회를 허용합니다.
- 직접도보, 대기, 좌석·입석, 승하차와 환승을 모두 양의 일반화 이동비용으로 평가합니다.
- 모든 설치 가능 후보를 **형평성 사전식 배분으로 exact evaluation**한 결과가 P0 기준해입니다.
- GNN은 후보를 top-k로 압축하고, 최종 후보는 exact solver로 다시 평가해 순위를 확정합니다.
- 강화학습은 여러 시설을 순차 배치하며 예산·공급 상태가 변하는 확장 단계에서 beam search·rollout과 함께 비교합니다.

즉, P0에서 GNN이나 강화학습이 임의의 시설 규모를 만들지 않습니다. 수요·용량·교통·필지 제약은 환경이 고정하고, AI는 실현 가능한 위치의 검색을 가속합니다.

## 문서 빌드

Node.js가 필요하며 별도 패키지 설치 없이 저장소에 포함된 KaTeX 런타임을 사용합니다.

```bash
node scripts/build-document-pages.mjs
```

이 명령은 다음 파일을 갱신합니다.

```text
content/planning.md                  → site/planning.html
content/technical-blueprint.md       → site/technical-blueprint.html
content/dual-graph-recommendation.md → site/dual-graph-recommendation.html
```

## 로컬 확인

```bash
python3 -m http.server 8000 --directory site
```

브라우저에서 `http://localhost:8000`을 열고 네 문서의 내비게이션, 표, 수식, 모바일 레이아웃과 외부 출처 링크를 확인합니다.

## 검증

빌드 스크립트 문법과 Markdown 변경의 공백 오류를 확인합니다.

```bash
node --check scripts/build-document-pages.mjs
git diff --check
```

원문과 생성물이 동기화됐는지는 빌드 전후 생성물 차이로 확인합니다. 깨끗한 작업 트리 또는 이미 갱신된 생성물을 기준으로 실행합니다.

```bash
node scripts/build-document-pages.mjs
git diff --exit-code -- \
  site/planning.html \
  site/technical-blueprint.html \
  site/dual-graph-recommendation.html
```

문서 변경만 있는 저장소이므로 별도의 애플리케이션 테스트·타입체크·linter는 현재 구성되어 있지 않습니다.
