# Elder Guardian Planning

복지 사각지대를 찾고 신규 복지시설의 위치와 수용량을 제안하는 모델링 방법론을 정리한 기술 보고서형 GitHub Pages 사이트입니다.

## 방법론 요약

교통망과 100m 격자 수요를 그래프로 표현하고, GNN 기반 강화학습 정책이 신규 시설의 위치와 규모를 결정합니다. 용량 제약 최소비용 흐름 알고리즘이 제안 결과의 미충족 인구, 이동비용, 설치비, 지역 간 형평성을 평가해 보상으로 반환합니다.

권장 구현 순서는 다음과 같습니다.

1. E2SFCA와 최소비용 흐름으로 설명 가능한 기준선 구성
2. GNN + 강화학습으로 시설 위치·수용량 선택 정책 학습
3. Graph Diffusion으로 조건별 복수 대안 생성
4. feasibility projection과 local search로 제약 위반 보정

## 로컬 확인

```bash
python3 -m http.server 8000 --directory site
```

브라우저에서 `http://localhost:8000`을 엽니다.
