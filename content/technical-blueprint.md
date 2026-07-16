# WelfareMap AI 기술 청사진

## 고령인구 복지 불균형 완화를 위한 시설 입지·수요 배분 시스템

> 문서 상태: P0 설계 확정안
>
> 기본 대상 시설: 도시지역 경로당
>
> 기본 의사결정: 지정 예산으로 신설 시설 1개 배치
>
> 핵심 원칙: 접근성 평균이 아니라 **미수용 수요와 접근성 최악 구간을 먼저 개선**한다.

---

## 1. 문제 정의

WelfareMap AI는 100m 격자별 예상 동시 이용자 수, 기존 시설의 동시수용량, 보행·대중교통망, 필지와 사업비 데이터를 이용해 다음 질문에 답한다.

1. 현재 어떤 격자의 수요가 용량 또는 접근성 때문에 충족되지 않는가?
2. 주어진 예산으로 어느 격자에 어느 규모의 경로당을 신설할 수 있는가?
3. 신설 후 미수용 수요와 장거리·고부담 이용자가 얼마나 감소하는가?
4. 평균적인 개선이 아니라 고령인구 복지 불균형이 실제로 완화되는가?

P0의 최적화 문제는 다음과 같이 정의한다.

> 대상 지역의 설치 가능한 후보 중 한 곳을 골라, 예산과 법규로 결정되는 최대 유효 용량을 추가하고, 형평성 우선 수요 배분 결과가 가장 좋아지는 입지를 선택한다.

### 1.1 확정된 기본 가정

| 항목 | P0 정의 |
|---|---|
| 공간 단위 | 100m × 100m 격자 하나가 의사결정 노드 하나 |
| 수요 | 격자·시간대·시나리오별 **예상 동시 이용자 수** |
| 기존 공급 | 같은 서비스 유형 시설의 동시수용량 합계 |
| 신규 시설 | 도시지역 경로당 1개 |
| 신규 용량 | 사용자가 직접 고르지 않고, 예산·필지·법규·면적당 수용량으로 결정 |
| 동일 격자 신설 | 허용. 실제로 별도 필지, 별도 건물 또는 적법한 증축안이 있어야 함 |
| 분석 대상 | 기본적으로 대상 자치구의 수요와 후보지 |
| 경로망 범위 | 행정경계로 자르지 않은 수도권 교통망 |
| 배분 원칙 | 미수용 최소화 → 최악 접근부담 완화 → 사각지대 완화 → 평균비용 최소화 |
| 다중 입지 | 상태를 갱신하며 반복 가능하되, 단순 greedy가 아닌 beam search·rollout 사용 |

### 1.2 시설 유형은 서로 대체 가능한 공급이 아니다

경로당, 노인복지관, 노인교실 등은 서비스와 이용 조건이 다르다. 따라서 모든 시설의 용량을 노드별 단일 숫자로 합치지 않는다.

$$
K_{i,q,t} = \sum_{f:\,node(f)=i,\,type(f)=q} K_{f,t}
$$

- $i$: 격자 노드
- $q$: 서비스 또는 시설 유형
- $t$: 시간대
- $K_{f,t}$: 시설 $f$의 시간대별 동시수용량

P0에서 신규 시설 유형은 `senior_center`(경로당)로 고정한다. 경로당 수요는 경로당과 실질적으로 대체 가능한 공급에만 배정한다. 다중 서비스 확장에서는 수요도 $d_{i,q,t,s}$로 분리한다.

---

## 2. 전체 시스템 구조

```mermaid
flowchart LR
    A["공공·행정·프로젝트 데이터"] --> B["정규화·품질검사·버전 고정"]
    B --> C["수도권 상태 확장 경로 그래프"]
    B --> D["100m 격자 의사결정 그래프"]
    C --> E["시간대·시나리오별 OD 비용 오라클"]
    E --> D
    D --> F["GNN Encoder"]
    F --> G["유효 후보 점수화"]
    G --> H["필지·예산 기반 면적·용량 결정"]
    H --> I["형평성 우선 Capacitated Min-Cost Flow"]
    E --> I
    I --> J["기준선 대비 Vector Reward·정책 지표"]
    J --> G
```

시스템은 역할이 다른 두 그래프를 사용한다.

1. **의사결정 그래프**: 100m 격자 간 수요·공급·공간 맥락을 GNN으로 표현한다.
2. **경로 그래프**: 정류장, 역, 노선, 방향, 정차순서, 탑승 상태를 보존해 실제 이동비용을 계산한다.

두 그래프를 합치지 않는 이유는 다음과 같다.

- 격자에 정류장을 압축하면 같은 격자의 다른 노선으로 비용 없이 순간이동할 수 있다.
- 하차 후 인접 격자를 거쳐 재탑승하면 환승 횟수를 회피할 수 있다.
- 방향과 정차순서가 사라지면 역방향 이동이나 존재하지 않는 직통 경로가 생긴다.
- GNN 메시지 전달에 필요한 관계와 최단경로 탐색에 필요한 상태 공간의 크기가 다르다.

---

## 3. 핵심 데이터 정의

### 3.1 수요

P0의 수요는 노인 인구 자체가 아니라 외부 수요 추정기가 산출한 예상 동시 이용자 수다.

$$
d_{i,t,s} \ge 0
$$

- $i$: 거주 100m 격자
- $t$: 운영시간 내 분석 시간대
- $s$: 수요·교통·시설 운영 시나리오

다중 서비스 확장:

$$
d_{i,q,t,s} \ge 0
$$

수요는 시나리오마다 변경할 수 있지만, 하나의 평가 에피소드 안에서는 불변이다. 입지 에이전트가 수요를 줄이거나 이동시키는 행동은 허용하지 않는다.

#### 권장 수요 산출 방식

$$
d_{i,t,s} = P^{65+}_{i} \cdot r_{i,s}^{eligible} \cdot p_{i,t,s}^{use} \cdot p_{i,t,s}^{peak}
$$

- $P^{65+}_{i}$: 65세 이상 인구
- $r^{eligible}$: 서비스 이용 가능 인구 비율
- $p^{use}$: 이용 의향 또는 실제 이용률
- $p^{peak}$: 같은 시간대에 시설에 머무를 확률

인구만 있을 때는 이를 수요로 확정하지 않고 prior와 상·중·하 시나리오를 만든다. 실제 회원 수, 일일 방문자 수, 월 방문 건수도 동시수용량 또는 동시수요와 같지 않으므로 체류시간과 시간대별 도착률을 통해 변환해야 한다.

100m 소지역 인구는 통계적 비밀보호 처리의 영향을 받을 수 있다. [SGIS 소지역 통계 이용 매뉴얼](https://sgis.kostat.go.kr/html/attachFiles/%EA%B0%9C%EC%A0%95%ED%8C%90%20SGIS%20%EC%86%8C%EC%A7%80%EC%97%AD%20%ED%86%B5%EA%B3%84%20%EC%9D%B4%EC%9A%A9%EB%A7%A4%EB%89%B4%EC%96%BC.pdf)에 따라 작은 격자 값을 절대적인 정답으로 간주하지 않고 공간 평활화와 민감도 시나리오를 함께 사용한다.

### 3.2 기존 시설 용량

시설 용량은 일일 방문객이나 등록회원 수가 아니라 같은 시간에 안전하게 서비스를 제공할 수 있는 인원이다.

```text
facility_id
source_record_id
service_type
grid_id
geometry
operational_status
availability_status
capacity_operational_confirmed
capacity_registered
capacity_fire
capacity_seats
capacity_operational
capacity_strict_unknown
capacity_legal_nominal
capacity_source
capacity_confidence
legacy_capacity_excluded
operating_calendar
eligible_resident_rule
facility_net_area_m2
facility_area_scope
facility_area_confidence
```

시간대별 유효용량은 다음처럼 계산한다.

$$
K_{f,t} = K_f^{sim} \cdot availability_{f,t}
$$

휴관 또는 해당 서비스가 운영되지 않는 시간에는 $availability_{f,t}=0$이다. 공간을 다른 프로그램과 공유하면 예약표를 이용해 0과 1 사이의 값으로 둔다.

행정 확인 전의 결측을 하나의 숫자로 숨기지 않는다.

- `STRICT_UNKNOWN`: 운영 여부와 운영 동시수용량이 함께 확인되지 않으면 0명
- `LEGAL_NOMINAL`: 운영불가로 확인된 시설은 0명, 나머지 결측 도시 경로당은 법정 최소 이용정원 20명을 민감도 값으로만 사용
- `legacy_capacity_excluded`: 과거 고정 8명과 전체 건축물 면적 기반 proxy는 `true`로 두고 공급 feature에서 차단

확인된 운영 동시수용량이 없으면 설치 신고정원을 확인 가능한 소방 수용인원과 좌석 수로 제한한다. 회원수·일 이용자·피크 관측 인원은 서로 다른 필드로 보존하고, 피크 관측값은 정원 검증과 신규 시설의 면적당 동시수용량 보정에 사용한다.

### 3.3 시나리오

최소 시나리오 축은 다음을 포함한다.

- 평일·주말 또는 운영일 유형
- 오전·오후 피크 시간대
- 수요 하·중·상
- 보행속도 하·중·상
- 배차간격 또는 운행시간의 정상·혼잡
- 좌석확률 하·중·상
- 엘리베이터 정상·고장 등 접근성 상태

정책 평가는 한 개 평균 시나리오가 아니라 주요 시나리오의 기대값과 최악 구간을 함께 보고한다.

---

## 4. Dual Graph 설계

### 4.1 100m 격자 의사결정 그래프

$$
G^{decision}_{t,s}=(V^{grid}, E^{relation}, X_{t,s}, E_f, g_{t,s})
$$

- $V^{grid}$: 100m 격자 노드
- $E^{relation}$: 공간·접근성 관계 간선
- $X_{t,s}$: 시간대·시나리오별 노드 특징
- $E_f$: 간선 특징
- $g_{t,s}$: 그래프 전역 특징

#### 4.1.1 노드 특징 스키마

| 그룹 | 필수 특징 |
|---|---|
| 식별·공간 | `grid_id`, 중심점, 행정구·동, 대상 지역 마스크, 좌표 positional encoding |
| 수요 | $d_{i,t,s}$, 65·75·85세 이상 인구, 독거·저소득·장애 등 취약성 특징, 수요 신뢰도 |
| 공급 | 서비스 유형별 시설 수, $K_{i,q,t}$, 잔여용량, 운영시간, 이용자격 |
| 기준선 접근성 | 최근접 시설 비용, 10·15·30분 내 공급량, 도달 가능한 시설 수, 미수용률, 사각지대율 |
| 교통 | 정류장·역 수, 노선 수, 방향별 운행 빈도, 저상버스 비율, 엘리베이터·에스컬레이터 |
| 보행환경 | 경사, 계단, 횡단보도, 보행로 단절, 대형도로·철도·하천 장벽, 보행 접근성 신뢰도 |
| 후보지 | 후보 상태, 유효 필지 수, 토지가격, 공공 소유 여부, 건폐율·용적률, 철거 필요 여부 |
| 신설안 | 예산 내 최대 연면적·순사용면적·용량·사업비, 법적 최소요건 충족 여부, 산정 신뢰도 |
| 중복 입지 | 기존 동종시설 존재 여부, 기존 용량, 별도 필지·증축 가능 여부 |
| 순차 의사결정 | 이미 신설된 용량, 남은 수요, 선택 순서, 후보 사용 여부 |

모든 연속형 변수는 학습 집합의 통계로 정규화하고, 결측 여부를 별도 mask feature로 전달한다. `UNKNOWN`을 0으로 대체해 설치 가능 또는 장벽 없음으로 오해하게 만들지 않는다.

#### 4.1.2 전역 특징

$$
g_{t,s}=[B_{remain}, k_{remain}, q, t, s, \sum_i d_i, \sum_i K_i,
\beta, G_\tau, G_{max}, T_{max}]
$$

- 남은 예산과 시설 수
- 목표 서비스 유형
- 시간대·시나리오 임베딩
- 총수요·총공급·현재 미수용량
- 일반화비용 계수 집합
- 선호 접근기준과 절대 상한

#### 4.1.3 간선 유형

의사결정 그래프의 간선은 실제 탑승 동작을 직접 표현하지 않는다.

| 관계 | 목적 | 주요 특징 |
|---|---|---|
| `spatial_4` 또는 `spatial_8` | 인접 수요·토지 맥락 전달 | 거리, 방향, 장벽 여부 |
| `walk_reachable` | 가까운 생활권 연결 | 최단 보행시간, 경사·계단 비용 |
| `transit_reachable` | 대중교통으로 연결된 생활권 전달 | 최소 일반화비용, 실제시간, 환승 수 |
| `same_admin` | 행정·정책 맥락 전달 | 동일 행정동·자치구 여부 |

밀집 그래프를 막기 위해 `walk_reachable`과 `transit_reachable`은 각 노드의 비용 기준 top-k와 임계값 내 연결만 유지한다. 단, 수요 배분용 OD 행렬은 GNN 간선으로 압축하지 않고 별도로 보존한다.

### 4.2 상태 확장 경로 그래프

경로 그래프는 수도권에서 필요한 범위 전체를 유지한다.

$$
G^{route}_{t,s}=(V^{state},E^{move}_{t,s})
$$

권장 상태는 다음과 같다.

```text
(physical_id, mode, route_id, direction_id, stop_sequence,
 onboard, previous_route_id, accessibility_state)
```

#### 4.2.1 상태와 간선

| 상태/간선 | 설명 |
|---|---|
| `grid` | 수요 또는 시설이 위치한 격자 |
| `walk_node` | 보행 네트워크 교차점·출입구 |
| `platform/stop` | 방향이 구분된 정류장·승강장 |
| `onboard(route,direction,seq)` | 특정 노선·방향·정차순서의 탑승 상태 |
| `walk` | 격자·보행노드·정류장·역 출입구 간 이동 |
| `board` | 최초 탑승 또는 환승 탑승, 대기비용 발생 |
| `ride` | 동일 노선·방향의 다음 정차지로 이동 |
| `alight` | 탑승 상태 종료 |
| `transfer_walk` | 출입구·승강장·정류장 간 환승 이동 |

`previous_route_id`는 짧은 보행이나 같은 격자 이동 뒤 재탑승해도 유지한다. 다른 노선·방향 또는 환승으로 정의된 재탑승에는 고정 환승 패널티를 한 번 부과한다.

#### 4.2.2 대기시간

배차간격이 $h$일 때 무작위 도착의 기본 기대대기는 $h/2$다.

$$
T^{wait}=h/2
$$

- 대기는 최초 `board`와 환승 `board`에서만 더한다.
- `ride` 구간마다 반복해서 더하지 않는다.
- 열차시각표 또는 차량 도착시각을 이용할 수 있으면 시간의존 최단경로로 대체한다.
- 막차·운행중단·긴 배차는 작은 상한값으로 잘라 비용을 과소평가하지 않는다. 시각표 기반으로 계산하거나 해당 출발시각의 탑승 불가 상태로 표현한다.

#### 4.2.3 구간 운행시간 결측

우선순위는 다음과 같다.

1. 노선·방향·정차순서·시간대별 관측 구간시간
2. 같은 노선·구간의 정상 평일 중앙값
3. 같은 교통수단·도로등급·거리 구간의 중앙속도
4. 거리 기반 보수적 추정치와 낮은 신뢰도 표시

평균보다 중앙값을 사용해 돌발 정체와 데이터 오류의 영향을 줄인다. 추정된 구간은 별도 flag를 저장하고 민감도 분석에 포함한다.

### 4.3 분석 경계 처리

수요와 신규 후보지는 대상 자치구로 제한할 수 있지만 경로 그래프는 자치구 경계에서 자르지 않는다.

```text
demand_mask(i)     = i가 대상 정책 지역의 수요 격자인가
candidate_mask(i)  = i가 대상 정책 지역의 설치 후보인가
routing_mask(i)    = 수도권 경로 탐색에 필요한 노드인가
facility_eligible(i,j) = 수요 i가 시설 j를 실제 이용할 수 있는가
```

따라서 광운대역에서 석계역으로 이동해 6호선을 타는 것처럼 경계 밖을 통과하는 경로가 보존된다. 반대로 노원구에서 구로구로 가는 배정은 행정구 경계를 무조건 금지해서가 아니라 다음 조건으로 자연스럽게 제외한다.

- 실제 이동시간 상한 초과
- 일반화비용 상한 초과
- 해당 시설의 거주지·회원 이용자격 불충족

인접 자치구의 가까운 시설은 이용자격이 허용되고 접근상한 안이면 배정할 수 있다. 공공 시설의 실제 운영규정은 `eligible_resident_rule`로 명시한다.

이를 위해 기존 시설 목록도 대상구 내부에서 자르지 않고, 최소한 대상 수요에서 $T_{max}$ 또는 $G_{max}$ 안에 도달 가능한 외부 시설까지 수집한다. 계산량을 줄이는 공간 buffer는 경로 계산 후의 보수적 도달가능 상한으로 만들며 단순 행정경계 buffer를 사용하지 않는다.

---

## 5. 고령자 일반화 이동비용

최단경로는 실제시간만이 아니라 고령자가 체감하는 부담을 최소화한다. 단위는 **좌석에 앉아 비혼잡 상태로 이동하는 1분 = 1 equivalent minute**로 둔다.

$$
\begin{aligned}
G(p)=&\ \beta_w T^{walk}
+\beta_{tw}T^{transfer\_walk}
+\beta_{wait}T^{wait}\\
&+\sum_e T_e^{ride}
\left[p_e^{seat}\beta_{seat}+(1-p_e^{seat})\beta_{stand}\right]\\
&+\kappa_{tr}N^{transfer}
+P^{stairs}+P^{slope}+P^{boarding}+P^{accessibility}
\end{aligned}
$$

모든 항은 0 이상이며 시간 계수는 양수다. 좌석의 편안함은 음의 비용이나 별도 보상으로 주지 않고, 입석·보행보다 낮은 양의 계수로 표현한다.

### 5.1 P0 기본값과 민감도 범위

| 매개변수 | 기본값 | 민감도 | 해석 |
|---|---:|---:|---|
| 지속 보행속도 | 0.85m/s | 0.70 / 0.85 / 1.12 | 이동취약 고령자 중심 계획값 |
| 일반 보행 $β_w$ | 1.50 | 1.50~2.00 | 직접도보 포함 |
| 대기 $β_{wait}$ | 1.75 | 1.60~2.50 | 좌석 차내시간 대비 |
| 환승보행 $β_{tw}$ | 2.00 | 1.80~2.20 | 역사 내 수직이동 포함 |
| 좌석·비혼잡 $β_{seat}$ | 1.00 | 0.80~1.00 | 비용의 기준, 항상 양수 |
| 좌석·혼잡 | 1.30 | 1.10~1.50 | 혼잡 불편 반영 |
| 입석 $β_{stand}$ | 1.60 | 1.40~2.40 | 낙상·피로 부담 반영 |
| 고정 환승 $κ_{tr}$ | 5분 | 0 / 5 / 8.2 / 11.2 | 계수 불확실성 공개 |
| 최대 환승 | 2회 | 1 / 2 / 제한 없음 | 기본은 2회, 비용상한도 병행 |
| 좌석확률 | 0.50 | 0.20 / 0.50 / 0.80 | 노선·시간대 자료가 없을 때 |

국내 연구에서 고령자의 평균 보행속도 약 1.12m/s와 더 보수적인 하위 구간 약 0.85m/s가 보고되어 P0 기본값은 0.85m/s로 둔다. [고령자 보행속도 연구자료](https://idea.seoul.go.kr/upload/suggest/20251127/64D4851EB32848C39BBDFE5FC3006D36.pdf)

교통수단별 정확한 고령자 계수는 지역·목적·건강상태에 따라 달라진다. [KTDB 통행시간가치 사례 보고서](https://www.ktdb.go.kr/DATA/pblcte/20160323084507431.pdf)의 접근 2.3, 대기 1.6, 차내 1.0, 환승횟수 8.2분 상당 값은 초기 prior로만 사용하고, 서울 고령자 대상 stated-preference 또는 revealed-preference 자료로 보정한다. 국내 표준 계수가 확정돼 있다고 가정하지 않는다.

서울 노인 조사에서는 계단·경사, 승하차, 앉을 곳 부족이 주요 외출 불편으로 나타났다. 따라서 이 항목은 단순 환승 횟수로 합치지 않고 경로별 장벽 특징으로 유지한다. [서울시 노인실태조사 원자료](https://kossda.snu.ac.kr/handle/20.500.12236/30286), [자치구 재분석 보고서](https://council.jungnang.go.kr/kr/bbs/download.do?bbs_id=active&uid=ABC300ABF0C990005BE090C1191909EF)

### 5.2 접근성 기준

P0에서는 시계시간과 일반화비용을 동시에 제한한다.

| 기준 | 기본값 | 목적 |
|---|---:|---|
| 선호 접근비용 $G_\tau$ | 15 equivalent min | 10분 직접도보 × 보행계수 1.5 |
| 실제시간 상한 $T_{max}$ | 30분 | 지나치게 먼 배정 차단 |
| 일반화비용 상한 $G_{max}$ | 45 equivalent min | 환승·장벽이 큰 짧은 경로 차단 |
| 실제시간 민감도 | 20 / 30 / 40분 | 정책 결론의 강건성 확인 |

서울의 경로당 평균 편도 이동시간이 약 10.5분으로 보고된 점을 바탕으로 10분 직접도보를 선호 기준으로 사용한다. 이는 법적 서비스권이 아니라 P0의 연구 가정이므로 10·15·30분 지표와 민감도 결과를 함께 공개한다. [서울 노인 이동·시설 접근 재분석](https://council.jungnang.go.kr/kr/bbs/download.do?bbs_id=active&uid=ABC300ABF0C990005BE090C1191909EF)

### 5.3 OD 오라클 출력

수요 격자 $i$와 시설 또는 후보 $j$마다 다음을 저장한다.

```text
origin_grid_id
destination_id
time_slice
scenario_id
clock_time_min
generalized_cost_min
walk_time_min
wait_time_min
ride_time_min
transfer_walk_min
transfer_count
seat_probability
barrier_components
path_signature
reachable
route_data_version
```

OD 비용은 GNN이 임의로 생성하지 않는다. 검증 가능한 경로 오라클의 결과를 입력 특징과 배분 제약으로 사용한다.

---

## 6. 후보지와 설치 가능성

100m 격자 전체를 곧바로 설치 가능 또는 불가능으로 판정하지 않는다. 필지·건축 가능안을 먼저 평가한 뒤 격자 후보로 집계한다.

### 6.1 후보 필지의 네 가지 상태

| 상태 | 의미 | 정책 추천 사용 |
|---|---|---|
| `FEASIBLE` | 공개·행정 데이터상 예산, 용도, 면적, 접도 등 필수 요건 충족 | 행동 가능 |
| `HARD_EXCLUDE` | 법적 용도상 건축 불가로 확인된 도로·하천·철도·공원 구역 또는 최소면적·예산 불충족 | 항상 마스킹 |
| `REVIEW_REQUIRED` | 도시계획·공원 내 예외·지구단위계획·고도·경관·보전 등 별도 심의 필요 | 기본 마스킹, 조건부 목록만 제공 |
| `UNKNOWN` | 핵심 필드 결측·충돌·갱신일 불명 | 기본 마스킹, 데이터 보강 대상 |

결측을 `FEASIBLE`로 간주하지 않는다. 최종 사업 후보는 공개데이터 분석 후에도 필지대장, 현장, 소유권, 지장물, 인허가 검토를 거쳐야 한다.

### 6.2 격자 후보 집계

한 격자 안에 여러 필지가 있으면 각 필지의 유효 건축안을 산정한다. P0의 격자 행동을 결정적으로 만들기 위해 다음 canonical plan을 사용한다.

1. 예산과 법규를 충족하는 안 중 신규 동시수용량 최대
2. 용량이 같으면 총사업비 최소
3. 사업비도 같으면 데이터 신뢰도 최대

해당 안을 $p_i^*$라 하고 노드 특징에 용량·면적·사업비를 기록한다. 동일 격자에 기존 경로당이 있어도 후보에서 제외하지 않는다. 다만 실제 별도 필지·건물·증축 가능성이 없으면 `HARD_EXCLUDE` 또는 `REVIEW_REQUIRED`다.

### 6.3 필수 토지·건축 특징

```text
parcel_id, grid_id, ownership_type, land_category, zoning
site_area_m2, appraised_land_price_per_m2
building_coverage_ratio, floor_area_ratio
road_access, demolition_required, existing_building_area
urban_plan_facility_type, river_park_rail_road_overlap
height_landscape_conservation_constraints
source_date, confidence, feasibility_status, exclusion_reason
```

---

## 7. 예산 → 면적 → 신규 용량

에이전트는 `50/100/200명` 같은 임의 용량을 선택하지 않는다. 위치별 토지·공사비와 법규를 적용한 환경 솔버가 예산 내 건축안과 용량을 결정한다.

### 7.1 총사업비

필지 $p$, 연면적 $A_g$인 신설안의 총사업비는 다음과 같다.

$$
\begin{aligned}
Cost(p,A_g)=&\ P^{land}_p A^{buy}_p
+C^{demolition}_p
+c^{build}(A_g,year)A_g\\
&+C^{design}+C^{supervision}+C^{equipment}
+C^{utility}+C^{permit}+C^{contingency}
\end{aligned}
$$

공사비 단가만으로 전체 예산을 계산하지 않는다. 토지, 철거, 설계, 감리, 가구·장비, 인입, 부담금, 물가상승, 예비비를 별도 항목으로 관리한다.

서울시 2024 공공건축물 가이드의 경로당·노인정 신축 공사비 기준은 다음과 같다.

| 연면적 | 2024년 3월 기준 공사비 |
|---|---:|
| 200㎡ 미만 | 385.2만원/㎡ |
| 200~400㎡ | 374.2만원/㎡ |
| 400㎡ 초과 | 368.5만원/㎡ |

이는 총사업비가 아닌 건축 공사비 기준이다. 실제 발주시점에는 최신 공식 가이드와 [KICT 건설공사비지수](https://www.kict.re.kr/menu.es?mid=a11001010000)로 보정한다. 원 단가는 [서울시 2024 공공건축물 건립 공사비 책정 가이드라인](https://opengov.seoul.go.kr/og/com/download.php?dname=2024%EB%85%84+%EA%B3%B5%EA%B3%B5%EA%B1%B4%EC%B6%95%EB%AC%BC+%EA%B1%B4%EB%A6%BD+%EA%B3%B5%EC%82%AC%EB%B9%84+%EC%B1%85%EC%A0%95+%EA%B0%80%EC%9D%B4%EB%93%9C%EB%9D%BC%EC%9D%B8.pdf&dtype=basic&nid=32033304&rid=F0000107846063&uri=%2Ffiles%2Fdcdata%2F100001%2F20241023%2FF0000107846063.pdf)을 따른다.

### 7.2 건축 가능 면적

예산 $B$에서 필지별 최대 연면적 $A_g^*$를 다음 제약으로 구한다.

$$
A_g^*(p,B)=\max A_g
$$

subject to

$$
Cost(p,A_g) \le B
$$

$$
A_g \le FAR_p \cdot A^{site}_p
$$

$$
A^{footprint} \le BCR_p \cdot A^{site}_p
$$

그리고 접도, 주차, 조경, 이격거리, 높이, 용도지역, 도시계획시설 및 현장 제약을 충족해야 한다. 단순화한 사전 추정식은 다음과 같지만 최종 후보 계산은 필지별 LP/MILP 또는 규칙 솔버로 수행한다.

$$
A_g \approx \min\left(A_{legal}^{max},
\frac{B-F_p}{c^{build}+P_p^{land}/FAR_p}\right)
$$

### 7.3 순사용면적과 수용량

$$
A_{program}=\eta_p A_g^* - A_{fixed}
$$

$$
K^{new}_p=\left\lfloor\frac{A_{program}}{a_{user,q}}\right\rfloor
=\left\lfloor\rho_q A_{program}\right\rfloor
$$

- $\eta_p$: 연면적 중 실제 프로그램 공간 비율
- $A_{fixed}$: 화장실·사무·창고 등 고정 필요면적
- $a_{user,q}$: 서비스 유형별 1인당 순사용면적
- $\rho_q=1/a_{user,q}$: 순사용면적 ㎡당 동시수용인원

`㎡당 몇 명`은 법정 상수가 아니다. 기존 운영시설 중 순사용면적과 실제 동시수용량이 모두 확인된 표본으로 추정한다.

1. 동일 시설·프로그램 유형만 사용
2. 회원수·일 방문자 수를 동시수용량으로 사용하지 않음
3. 비정상 기록과 5·95백분위 밖 극단값 검토
4. 정책 계획에는 보수적인 $a_{user}$ 75백분위 사용
5. bootstrap 신뢰구간으로 용량 하·중·상 시나리오 생성

도시지역 경로당은 법정 최소 이용정원 20명 등 현행 시설기준을 충족해야 한다. 법은 보편적인 `인원/㎡` 비율을 제공하지 않으므로 최소 정원과 공간 기준을 밀도 추정치로 오해해서는 안 된다. [노인복지법 시행규칙](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=282119)과 [노인여가복지시설 시설기준 별표 7](https://www.law.go.kr/LSW/flDownload.do?bylClsCd=110201&flSeq=43368529&gubun=)을 별도 법적 검증 규칙으로 둔다.

### 7.4 신규 시설 적용

선택 격자 $i$의 시설 유형 $q$ 용량만 증가시킨다.

$$
K'_{i,q,t}=K_{i,q,t}+K^{new}_{i,q}\cdot availability^{new}_t
$$

기존 시설과 같은 격자여도 단순 합산이 가능하나, 원본 시설 레코드와 신규 시설 레코드는 유지해 운영시간·이용자격을 잃지 않는다.

---

## 8. 수요 배분 알고리즘

입지 평가는 시설 이용률 균등화가 아니라 실제 수요 보전, 용량, 접근성, 이용자격을 만족하는 capacitated min-cost flow로 수행한다.

수요 격자 $i$, 시설 $j$, 시간대 $t$, 시나리오 $s$에 대해:

$$
x_{ijts}\ge0,\qquad u_{its}\ge0
$$

- $x_{ijts}$: 격자 $i$에서 시설 $j$로 배정된 예상 동시 이용자
- $u_{its}$: 접근 또는 용량 부족으로 미배정된 수요

### 8.1 제약식

수요 보전:

$$
\sum_j x_{ijts}+u_{its}=d_{its}
$$

시설 용량:

$$
\sum_i x_{ijts}\le K_{j,q,t}
$$

접근성과 이용자격:

$$
x_{ijts}=0
\quad\text{if}\quad
T_{ijts}>T_{max}
\ \lor\ G_{ijts}>G_{max}
\ \lor\ eligible(i,j,q,t)=0
$$

수요와 용량이 사람 단위 정수이면 min-cost flow의 정수성을 사용한다. 확률적 기대수요이면 LP 연속변수로 풀고 결과를 기대 인원으로 해석한다.

### 8.2 형평성 지표

미배정도 접근부담에 포함하기 위해 미배정 비용 $G_{unserved}>G_{max}$를 고정한다.

$$
b_{its}=\frac{\sum_j G_{ijts}x_{ijts}+G_{unserved}u_{its}}
{\max(d_{its},\epsilon)}
$$

선호 접근기준을 넘는 사각지대 비율:

$$
z_{its}=\frac{u_{its}+\sum_jx_{ijts}\mathbf{1}[G_{ijts}>G_\tau]}
{\max(d_{its},\epsilon)}
$$

전체 사각지대 수요 비율:

$$
Z_{ts}=\frac{\sum_i u_{its}+\sum_{i,j}x_{ijts}\mathbf{1}[G_{ijts}>G_\tau]}
{\max(\sum_i d_{its},\epsilon)}
$$

해당 시간대·시나리오의 총수요가 0이면 $Z_{ts}=0$으로 반환하고 CVaR 표본에서도 제외한다.

최악 구간은 수요 또는 취약성 가중 $CVaR_{0.9}(b)$로 측정한다. CVaR는 상위 10% 고부담 이용자를 평균해 한두 개 극단값보다 안정적이면서 평균비용이 가리는 불평등을 드러낸다.

### 8.3 Lexicographic objective

배분과 후보 비교는 다음 순서를 엄격히 따른다.

1. $L_1=\sum_i u_i$: 총 미수용 수요 최소화
2. $L_2=CVaR_{0.9}(b)$: 고부담 상위 10% 최소화
3. $L_3=Z$: 선호 접근기준 밖 사각지대 최소화
4. $L_4=\frac{\sum_{ij}G_{ij}x_{ij}}{\sum_{ij}x_{ij}}$: 배정된 수요의 평균 일반화비용 최소화
5. $L_5=Cost$: 같은 효과일 때 총사업비 최소화

$$
J=(L_1,L_2,L_3,L_4,L_5)
$$

두 후보는 $J$의 앞 항목부터 비교한다. 단일 임의 가중합으로 바꾸면 작은 평균시간 개선이 미수용 증가를 상쇄할 수 있으므로 P0의 정책 순위를 보장하지 못한다.

취약계층 우선 정책이 필요하면 $L_2$와 $L_3$의 분포 가중치에 취약성 계수를 사용하되, 기본 수요 보전식이나 전체 수요 분모를 변경하지 않는다.

### 8.4 시간대·시나리오 집계

각 $(t,s)$에 대해 독립적으로 제약을 지킨 배분 결과 $L_{k,t,s}$를 구한다. 특정 평균 시나리오에서만 좋은 후보가 선택되지 않도록 P0의 기본 집계는 지표별 시나리오 CVaR와 기대값을 함께 사용한다.

$$
J^{robust}=\left(
CVaR^{scenario}_{0.9}(L_1),\mathbb E[L_1],
CVaR^{scenario}_{0.9}(L_2),\mathbb E[L_2],
CVaR^{scenario}_{0.9}(L_3),\mathbb E[L_3],
\mathbb E[L_4],L_5
\right)
$$

시나리오 확률을 알면 검증된 확률을 사용하고, 모르면 동일 가중치와 정책상 필수 스트레스 시나리오를 함께 보고한다. 시나리오 수가 적어 CVaR가 사실상 최악값이 되는 경우에는 결과에 이를 명시한다. 후보 간 비교는 여전히 앞 항목의 악화를 뒤 항목이 상쇄하지 못하는 사전식 순서를 따른다.

### 8.5 솔버 구현

- 1차: OR-Tools min-cost flow 또는 LP
- CVaR: 보조변수를 추가한 선형식
- 사전식 최적화: 각 단계의 최적값을 다음 단계의 제약으로 고정하고 순차 풀이
- 대규모 반복평가: OD·기준선 네트워크 캐시, warm start, 후보 병렬화
- 재현성: 동일 입력에는 동일 tie-break와 결과를 반환

---

## 9. 보상과 학습 목표

### 9.1 기준선 대비 Vector Reward

기존 시설만 배분한 목적벡터를 $J^0$, 후보 $a$를 신설한 뒤를 $J^a$라고 한다. 시나리오가 여러 개면 8.4절의 $J^{robust}$를 사용한다.

$$
R(a)=\left(
U^0-U^a,
CVaR^0-CVaR^a,
Z^0-Z^a,
\bar G^0-\bar G^a,
-Cost(a)
\right)
$$

구현상 보상은 다음 벡터로 저장한다.

```text
reward_unserved_improvement
reward_cvar90_improvement
reward_blindspot_improvement
reward_mean_cost_improvement
reward_cost_tiebreak
```

정책 선택도 같은 사전식 우선순위를 사용한다. 스칼라가 필요한 알고리즘에서는 각 항을 정상화한 뒤 앞 단계의 1단위 악화를 뒤 단계 전체 개선으로 보상할 수 없도록 dominance bound를 설정한다. 단순히 경험적인 `λ1+λ2+...` 가중합을 기본 보상으로 사용하지 않는다.

### 9.2 GNN 출력 헤드

$$
h_i^{(0)}=MLP(x_i)
$$

관계형 메시지 전달의 한 예:

$$
h_i^{(l+1)}=LayerNorm\left(h_i^{(l)}+
\sum_{r}\sum_{j\in\mathcal N_r(i)}
\alpha_{ijr}W_rh_j^{(l)}\right)
$$

출력은 하나의 불투명한 점수가 아니라 목적별 head로 분리한다.

- `Δunserved_head`
- `Δcvar90_head`
- `Δblindspot_head`
- `Δmean_cost_head`
- `feasibility/calibration_head`

후보 점수는 마스킹 후 lexicographic comparator로 정렬한다. 다중 head는 어떤 이유로 후보가 추천됐는지 설명하고 특정 지표의 오차를 따로 교정할 수 있게 한다.

### 9.3 입력 누수 방지

후보 $i$를 실제로 설치한 뒤 계산되는 다음 값은 GNN 입력으로 넣지 않는다.

- 설치 후 미수용 수요
- 설치 후 CVaR
- 설치 후 사각지대율
- 최적 후보 순위 또는 솔버 목적값

이 값은 label과 보상으로만 사용한다. 입력에는 설치 전 기준선 특징과 후보 자체의 비용·용량만 허용한다.

### 9.4 행동과 마스킹

P0의 행동은 임의 용량이 아니라 격자 하나다.

$$
a=i,\qquad
\mathcal A=\{i\mid status_i=FEASIBLE,\ Cost(p_i^*)\le B,
\ K_i^{new}\ge K_{legal}^{min}\}
$$

`HARD_EXCLUDE`, `REVIEW_REQUIRED`, `UNKNOWN`, 예산 초과, 법정 최소규모 미달 후보는 soft penalty가 아니라 확률 계산 전에 마스킹한다. 기존 동종 시설이 있다는 이유만으로 격자를 마스킹하지 않는다. 동일 격자 신설 가능성은 별도 필지·건축안의 `FEASIBLE` 판정으로 결정한다.

---

## 10. Reward Hacking 방지 불변식

보상 해킹 방지는 학습 경향이 아니라 환경과 테스트가 강제하는 불변식이다.

### 10.1 경로 불변식

1. 모든 OD에 직접도보 경로를 항상 포함한다.
2. 교통수단 탑승 자체에는 보상을 주지 않는다.
3. 모든 이동 간선 비용은 0 이상이고 시간 간선은 양수다.
4. 좌석 차내시간도 양의 비용이며, 보행·입석보다 낮을 수만 있다.
5. 대기비용은 `board`에서만 한 번 발생한다.
6. 다른 노선·방향 재탑승은 짧은 도보를 끼워도 환승으로 기록한다.
7. 음의 순환과 무비용 순환을 금지하고, 지배되는 loop 경로를 제거한다.
8. transit 경로는 직접도보보다 실제 목적함수가 좋을 때만 선택된다.
9. 엘리베이터가 없거나 고장인 접근불가 경로를 단순 계단 페널티로 통과시키지 않는다.

### 10.2 배분·보상 불변식

1. 모든 수요는 배정 $x$ 또는 미배정 $u$로 보존된다.
2. 미도달 수요를 데이터에서 삭제하거나 분모에서 제외하지 않는다.
3. 보상의 분모는 설치 전 전체 수요로 고정한다.
4. 시설 용량, 수요, 배차, 좌석확률은 입지 행동으로 변경할 수 없다.
5. 시설 유형이 다른 용량끼리 합산하지 않는다.
6. 회원수·일 이용량을 동시수용량으로 대체하지 않는다.
7. 시설 이용률 분산이나 만석률을 직접 보상하지 않는다.
8. 설치 전후는 동일한 수요·교통 시나리오와 난수 seed로 비교한다.
9. 수요 유발효과는 별도 사후 시나리오로만 계산하고 설치 후 수요 감소로 보상하지 않는다.
10. 제약 위반 후보는 큰 페널티가 아니라 action mask로 원천 차단한다.

### 10.3 단조성 기대

동일 조건에서 유효 용량을 추가했을 때 $L_1$은 악화되어서는 안 된다. 더 가까운 동등 시설이 추가됐을 때 기존 이용자에게 더 먼 배정을 강요해서는 안 된다. 이 성질이 깨지면 학습 문제가 아니라 배분 솔버 또는 tie-break 구현 오류로 취급한다.

---

## 11. P0: 단일 시설 정확 열거

후보지가 유한하고 신규 시설이 1개이면 강화학습 없이 정확 평가할 수 있다. 이것을 P0의 정답 생성기와 감사 가능한 기준선으로 사용한다.

### 11.1 알고리즘

```text
입력: 기준선 수요 d, 기존 용량 K, 예산 B, FEASIBLE 후보 C

1. 기존 시설만으로 모든 (t,s)의 baseline allocation과 J0 계산
2. 각 후보 i ∈ C에 대해
   a. canonical parcel plan p*i와 신규 용량 Knew_i 계산
   b. K' = K + Knew_i
   c. 동일 OD·수요 시나리오에서 allocation 재계산
   d. Ja와 vector improvement J0 - Ja 저장
3. 시나리오 집계 규칙에 따라 후보를 lexicographic 정렬
4. 상위 후보, 지표별 개선, 영향을 받은 격자, 불확실성 구간 반환
```

후보 수가 많아도 OD와 기존 네트워크를 캐시하고 후보를 병렬 평가할 수 있다. 정확 열거 결과는 다음에 사용한다.

- 정책 담당자에게 직접 제공하는 P0 추천
- GNN 지도학습 label
- 휴리스틱·GNN·RL의 optimality gap 기준
- 보상 해킹 회귀 테스트

### 11.2 GNN의 P0 역할

GNN은 정확 솔버를 대체해 정답을 만드는 것이 아니라, 대규모 시나리오에서 유망 후보를 빠르게 추리는 surrogate다.

1. 정확 열거 데이터로 다중 head를 지도학습
2. 추론 시 GNN 상위 $k$개 후보 생성
3. 상위 후보를 정확 배분 솔버로 재평가
4. 최종 순위는 솔버 결과로 확정

### 11.3 다중 시설 확장

$m>1$에서는 P0의 `한 후보가 전체 예산에서 만들 수 있는 최대용량`을 그대로 반복하면 첫 시설이 예산을 모두 사용할 수 있다. 따라서 각 필지에서 서로 지배되지 않는 `(사업비, 동시수용량)` 건축안의 Pareto 집합을 먼저 만든다.

```text
candidate_plan_option = (parcel_id, grid_id, gross_area, total_cost, capacity)
```

다중 입지의 행동은 임의 용량 숫자가 아니라 이 솔버가 만든 적법한 plan option을 선택한다. 같은 격자도 사용하지 않은 별도 필지·건축안이 남아 있으면 다시 선택할 수 있다. 한 plan을 선택한 후 다음 상태를 갱신한다.

$$
B_{r+1}=B_r-Cost(a_r)
$$

$$
K_{r+1}=K_r+K^{new}(a_r)
$$

$$
s_{r+1}=UpdateGraph(s_r, Allocation_{r+1})
$$

그러나 매 단계의 1등 후보만 선택하는 greedy는 첫 시설이나 면적 선택이 후속 선택 가능성을 막을 수 있다. 위치와 예산 배분을 함께 탐색하는 권장 순서는 다음과 같다.

- 작은 후보·시설 수: 조합 열거 또는 MILP
- 중간 규모: beam search + 정확 배분 rollout
- 큰 규모: GNN pointer policy 또는 PPO로 후보 생성 + beam search
- 최종안: swap/add/drop local search와 정확 솔버 재검증

`STOP`은 남은 예산으로 법적 최소규모를 충족하는 후보가 없거나 추가 입지가 정책 목적을 개선하지 않을 때만 허용한다.

---

## 12. 데이터 파이프라인

### 12.1 원천 데이터

| 영역 | 우선 데이터 | 사용 목적 |
|---|---|---|
| 100m 고령인구 | [SGIS OpenAPI](https://www.data.go.kr/data/15021230/openapi.do), [SGIS API 정의서](https://sgis.kostat.go.kr/developer/upload/doc/SGIS_OpenAPI_%EC%A0%95%EC%9D%98%EC%84%9C.pdf) | 65세 이상 인구 prior·수요 특징 |
| 노인 수요 조사 | [2024 서울시 노인실태조사](https://kossda.snu.ac.kr/handle/20.500.12236/30284), [2023 노인실태조사 공공데이터](https://www.data.go.kr/tcs/dss/selectFileDataDetailView.do?publicDataPk=15004296) | 이용률·외출·교통수단·취약성 보정 |
| 경로당 명부 | [서울시 경로당 정보](https://data.seoul.go.kr/dataList/OA-15052/S/1/datasetView.do) | 시설명·주소·전화·담당기관의 기준 원천. 행별 좌표·면적·정원·운영상태는 별도 확보 |
| 경로당 현행성·용량 | 25개 자치구 설치·변경 신고대장, 현장 피크 표본 | 운영상태, 신고정원, 소방 수용인원, 좌석, 순사용면적, 동시이용자 |
| 수도권 대중교통 기반망 | [KTDB 전국 대중교통 GTFS](https://www.ktdb.go.kr/www/selectBbsNttView.do?bbsNo=2&key=45&nttNo=3785) | 행정경계 밖 노선·정류장 topology |
| 버스 노선 | [서울 버스 노선 API](https://data.seoul.go.kr/bsp/wgs/dataView/data300View/20049.do), [TAGO 버스 노선 API](https://www.data.go.kr/data/15098529/openapi.do) | 노선·방향·정차순서·배차 |
| 버스 구간시간 | [국토교통부 버스도착정보 API](https://www.data.go.kr/data/15000314/openapi.do) | 시간대별 구간시간·도착정보 |
| 지하철 구간 | [서울 지하철 역간 거리·소요시간](https://data.seoul.go.kr/dataList/OA-12034/S/1/datasetView.do) | 방향별 철도 ride edge |
| 지하철 시각표 | [서울교통공사 열차운행시각표](https://data.seoul.go.kr/dataList/OA-22750/A/1/datasetView.do) | 시간의존 대기·운행 |
| 혼잡 | [서울 지하철 혼잡도](https://data.seoul.go.kr/dataList/OA-12928/A/1/datasetView.do) | 좌석확률·혼잡 계수 시나리오 |
| 보행·교통약자 | 서울 역사 승강시설, 보행자도로망, 경사·계단·횡단보도 | 접근불가와 장벽비용 |
| 필지 | [연속지적도 API](https://www.data.go.kr/data/15123894/openapi.do?recommendDataYn=Y) | 필지 경계·면적·후보 집계 |
| 토지이용 | [국가공간정보 토지이용·용도지역 데이터](https://www.data.go.kr/dataset/15021101/fileData.do) | 설치 제한·건폐율·용적률 |
| 지가 | [서울 개별공시지가](https://data.seoul.go.kr/dataList/catalogView.do?currentPageNo=1&infId=OA-1180&srvType=A) | 필지별 토지비 추정 |
| 공사비 | [서울 공공건축물 공사비 가이드](https://news.seoul.go.kr/citybuild/technical/construction_cost_estimation_guidelines) | 시설 유형·규모별 공사비 |

현재 고정한 서울시 원본은 2025년 6월 말 기준 3,644건이며 행별 좌표·면적·정원·운영상태를 제공하지 않는다. 2026-07-17 시설 master에는 P0 좌표값 3,644건이 모두 존재하지만 엄격 검증 완료는 2건이고 3,642건은 검토가 남아 있다. 확인된 운영 동시수용량은 0건, 운영상태 미확인은 3,640건이다. 따라서 좌표 coverage를 검증 완료로 표현하지 않고, 자치구 회신 전에는 `STRICT_UNKNOWN`과 `LEGAL_NOMINAL`의 후보 순위 안정성을 함께 보고한다.

원본, 좌표 근거, 수동 보정, 용량 회신은 `source_record_id`로 연결하고 기준일과 근거 URL을 시설별로 기록한다. 회신 병합 시 중복·미등록 ID, 음수·분수 인원, 근거 누락, 검증되지 않은 전체 건축물 면적을 오류로 차단한다.

### 12.2 ETL 단계

1. **수집**: API 원본과 파일을 변경 없이 snapshot 저장
2. **좌표 통일**: 원본 CRS 보존 후 분석 CRS로 변환
3. **시간 정규화**: 기준일, 평일·주말, 시간대, 운행 예외 통일
4. **식별자 연결**: 정류장·노선·방향·정차순서와 역·승강장 canonical ID 생성
5. **공간 조인**: 수요·시설·필지를 100m 격자에 연결
6. **품질 검사**: 중복, 누락 순번, 역방향, 비정상 좌표, 음의 시간, 용량 단위 검사
7. **경로 그래프 생성**: 수도권 상태 확장 graph snapshot 생성
8. **OD 생성**: 시간대·시나리오별 수요 격자–시설·후보 비용 계산
9. **후보 솔버**: 필지 상태와 예산별 canonical plan 생성
10. **Dataset manifest**: 원천 URL, 수집시각, 해시, 스키마 버전, 변환 코드 버전 기록

### 12.3 권장 저장 스키마

- PostgreSQL + PostGIS: `grid`, `facility`, `parcel`, `candidate_plan`, `stop`, `station`
- columnar file: `route_edge`, `od_cost`, `demand_scenario`, `allocation_result`
- object storage: 원본 snapshot, graph tensor, 모델 artifact
- experiment registry: 데이터 버전, 파라미터, seed, 솔버 버전, 지표

`od_cost`와 `candidate_plan`은 입력 데이터 버전, 예산, 시간대, 일반화비용 파라미터의 hash로 캐시를 구분한다.

---

## 13. API 계약

### 13.1 현재 상태 분석

`POST /v1/analyses/baseline`

```json
{
  "region_id": "seoul-nowon",
  "service_type": "senior_center",
  "time_slices": ["weekday_am", "weekday_pm"],
  "scenario_ids": ["demand_mid_walk_085", "demand_high_walk_070"],
  "thresholds": {
    "preferred_generalized_min": 15,
    "max_clock_min": 30,
    "max_generalized_min": 45
  }
}
```

응답은 총수요, 미수용, CVaR90, 사각지대율, 평균 일반화비용과 격자별 결과를 반환한다.

### 13.2 단일 시설 추천

`POST /v1/recommendations/single-facility`

```json
{
  "region_id": "seoul-nowon",
  "service_type": "senior_center",
  "budget_krw": 3000000000,
  "candidate_policy": "feasible_only",
  "routing_scope": "seoul_metro_full",
  "evaluation": {
    "method": "exact_enumeration",
    "scenario_aggregation": "lexicographic_robust",
    "top_k": 10
  }
}
```

후보별 핵심 응답:

```json
{
  "grid_id": "G21045",
  "candidate_plan_id": "CP-G21045-2026Q3",
  "feasibility_status": "FEASIBLE",
  "gross_floor_area_m2": 238.4,
  "program_area_m2": 151.2,
  "simultaneous_capacity": 61,
  "estimated_total_cost_krw": 2975000000,
  "improvement": {
    "unserved": 55,
    "cvar90_equivalent_min": 4.2,
    "blindspot_ratio_point": 0.031,
    "mean_generalized_min": 1.1
  },
  "affected_grid_ids": ["G10293", "G10294"],
  "uncertainty": {
    "capacity_low": 48,
    "capacity_mid": 61,
    "capacity_high": 72
  }
}
```

예시 숫자는 API 형식 설명용이며 실제 정책값이 아니다.

### 13.3 감사 가능성

모든 응답에 다음 필드를 포함한다.

```text
dataset_manifest_id
routing_graph_version
demand_model_version
cost_model_version
capacity_calibration_version
solver_name_and_version
parameter_set_id
random_seed
generated_at
```

---

## 14. 검증과 테스트

### 14.1 데이터 검증

- 격자 ID와 geometry의 유일성
- 시설·필지 point-in-polygon 결과와 경계점 처리
- 수요·용량 단위가 모두 동시 인원인지 확인
- 노선별 방향과 정차순서의 연속성
- 구간 운행시간과 배차간격이 양수인지 확인
- 역·정류장 좌표 이상치와 중복 ID 확인
- 대상구 밖 경로 노드가 전처리 중 잘리지 않는지 확인
- 후보 상태의 근거와 exclusion reason 누락 검사
- 원천 기준일과 데이터 hash 재현성 검사

### 14.2 경로 단위 테스트

1. 가까운 목적지에서 직접도보가 후보로 존재한다.
2. 같은 노선 연속 구간에는 환승 패널티가 없다.
3. 최초 탑승 대기는 한 번만 부과된다.
4. 하차–짧은 보행–다른 노선 탑승에 환승이 정확히 한 번 부과된다.
5. 루프를 추가해도 경로비용이 낮아지지 않는다.
6. 좌석확률 증가 시 비용은 낮아질 수 있지만 음수가 되지 않는다.
7. 계단만 존재하고 계단 이용 불가인 시나리오에서는 경로가 차단된다.
8. 광운대–석계 등 행정경계 밖을 통과하는 합법 경로가 탐색된다.
9. 노원–구로 같은 장거리 경로는 시간 또는 일반화비용 상한으로 배정되지 않는다.

### 14.3 배분 솔버 테스트

- 모든 격자에서 $\sum_jx_{ij}+u_i=d_i$
- 모든 시설에서 $\sum_ix_{ij}\le K_j$
- 이용자격·시간·비용 상한 위반 배정이 0
- 수요 0, 용량 0, 시설 0, 후보 0인 경계조건
- 총용량이 충분한 단일 시설, 부족한 단일 시설, 경쟁하는 복수 시설
- 가까운 희소 시설을 대안이 없는 수요에 남겨두는 형평성 사례
- lexicographic 앞 항목의 악화를 뒤 항목 개선으로 선택하지 않는지 확인
- CVaR 구현을 작은 수기 계산 예제와 비교
- 같은 입력과 tie-break에서 결과가 완전히 재현되는지 확인

### 14.4 비용·용량 테스트

- 예산 증가 시 같은 필지의 최대 가능 면적·용량이 감소하지 않음
- 토지가격 또는 공사비 증가 시 최대 가능 용량이 증가하지 않음
- 건폐율·용적률·최소 시설기준 위반안 차단
- `REVIEW_REQUIRED`, `UNKNOWN`, `HARD_EXCLUDE` 기본 action mask 확인
- 기존 시설 격자라도 별도 유효 필지가 있으면 후보가 될 수 있음
- 회원수나 일 이용자 수 필드를 용량으로 읽지 않음
- 공사비 단가 구간 경계에서 총비용이 불연속적으로 역전되지 않음

### 14.5 Reward Hacking 회귀 테스트

- 무의미한 버스 탑승을 추가한 경로가 직접도보보다 유리해지지 않음
- 환승 회피용 하차·재탑승이 패널티를 제거하지 못함
- 미도달 수요를 삭제해 보상이 올라가지 않음
- 시설 이용률을 맞추기 위한 원거리 배정이 선택되지 않음
- 신규 시설 용량을 과대 보고해도 환경의 필지 솔버 값으로 덮어씀
- 수요 분모가 설치 전후 동일함
- 같은 시나리오에서 용량 추가가 미수용 수요를 증가시키지 않음

### 14.6 모델 평가

비교 베이스라인:

- 무작위 유효 후보
- 노인 인구 또는 예상수요 최대 격자
- 현재 미수용 최대 격자
- greedy 최대 커버리지
- p-median 또는 maximal covering
- MILP 또는 단일 입지 정확 열거
- GNN 지도학습
- GNN + 정확 top-k 재평가

필수 지표:

- 총 미수용 수요와 커버리지율
- CVaR90 일반화비용
- $G_\tau$ 밖 사각지대 수요 비율
- 평균·중앙·90백분위 실제시간과 일반화비용
- 취약계층별 동일 지표
- exact enumeration 대비 후보 recall@k와 regret
- 시나리오 최악값, 평균값, 순위 안정성
- 전처리·OD·배분·전체 추천 소요시간

검증 분할은 임의 격자 분할이 아니라 공간·시간 기준으로 수행한다. 한 자치구로 학습하고 다른 자치구에서 평가하거나, 과거 시점으로 학습해 미래 시점으로 평가해 공간 누수와 시간 누수를 막는다.

---

## 15. 구현 로드맵

### Phase 0 — 정의와 데이터 감사

- 서비스 유형을 경로당으로 고정
- 수요·용량 단위를 예상 동시 인원으로 통일
- 시설별 용량 출처와 신뢰도 작성
- 주요 시간대·시나리오와 이용자격 규칙 확정
- 필지 데이터로 네 가지 후보 상태 생성
- 현재 공사비와 법적 기준 버전 고정

완료 조건: 샘플 격자·시설·필지·노선이 원천까지 역추적되고 단위 검사가 통과한다.

### Phase 1 — 경로와 OD 오라클

- 수도권 노선·방향·정차순서 그래프 구축
- 보행 접근과 역사 내 수직이동 연결
- 상태 확장 환승과 대기비용 구현
- 일반화비용 파라미터 세트 구현
- 수요 격자–기존 시설·후보 OD 캐시 생성

완료 조건: 경계 밖 경로, 환승, 직접도보, 접근불가 사례의 golden test가 통과한다.

### Phase 2 — 후보 사업비·용량 솔버

- 필지별 hard/review/unknown 판정
- 예산별 연면적·총사업비 산정
- 실제 시설 표본으로 $a_{user}$ 보정
- 격자별 canonical plan 생성

완료 조건: 면적·비용·용량 단조성과 법적 최소요건 테스트가 통과한다.

### Phase 3 — 정확 배분과 단일 입지 P0

- capacitated min-cost flow 구현
- CVaR와 사각지대 지표 구현
- 순차 풀이 방식 lexicographic objective 구현
- 모든 `FEASIBLE` 후보 정확 열거
- 정책 지도와 상위 후보 근거 생성

완료 조건: 제약식, 수기 예제, reward-hacking 회귀 테스트가 통과하고 결과가 재현된다.

### Phase 4 — GNN surrogate

- 격자 관계 그래프와 전역 특징 생성
- 관계형 GNN과 다중 목적 head 구현
- 정확 열거 결과로 지도학습
- top-k exact reranking 구현
- 공간·시간 외삽 성능 및 calibration 평가

완료 조건: exact 후보 recall@k와 regret 목표를 사전에 정한 임계값 이상 달성한다.

### Phase 5 — 다중 입지

- 남은 예산·용량·배분 상태 갱신
- beam search 또는 exact rollout
- swap/add/drop local search
- 필요할 때만 PPO·pointer policy 비교

완료 조건: 작은 문제에서 MILP 최적해와 비교하고, greedy보다 안정적으로 우수함을 확인한다.

### Phase 6 — 정책 서비스

- baseline·recommendation API
- 설치 전후 지도와 수혜·비수혜 격자 설명
- 파라미터·데이터·솔버 버전 감사 로그
- 민감도와 불확실성 구간 표시
- 필지 현장검토 workflow 연동

---

## 16. P0 완료 기준

P0는 다음 조건을 모두 만족할 때 완료된 것으로 본다.

1. 모든 입력 수요와 시설 용량이 예상 동시 인원 단위다.
2. 경로 그래프가 대상 자치구 밖의 유효한 수도권 경로를 보존한다.
3. 방향·정차순서·최초대기·환승이 상태 확장 그래프로 정확히 계산된다.
4. 직접도보와 좌석·입석의 양의 비용이 보상 해킹 테스트를 통과한다.
5. 후보 필지가 네 상태로 분류되고 `FEASIBLE`만 기본 추천에 들어간다.
6. 위치별 신규 면적·용량이 예산, 토지비, 공사비, 법규에서 재현 가능하게 산출된다.
7. 배분 결과가 수요 보전, 용량, 접근상한, 이용자격을 모두 만족한다.
8. 미수용 → CVaR90 → 사각지대 → 평균비용 순의 정책 우선순위가 보장된다.
9. 단일 시설의 모든 유효 후보가 정확 평가되고 상위 후보의 개선 근거가 공개된다.
10. 데이터·파라미터·코드·솔버 버전이 고정되어 같은 결과를 재생성할 수 있다.

---

## 17. 최종 형식 정의

P0의 최적 입지는 다음과 같다.

$$
a^*=\operatorname*{lexmin}_{a\in\mathcal A_{FEASIBLE}(B)}
J\left(Allocate\left(d,
K+K^{new}(a,B),
OD(G^{route})\right)\right)
$$

여기서:

- $\mathcal A_{FEASIBLE}(B)$: 예산과 필지·법규를 충족하는 격자 후보
- $K^{new}(a,B)$: 후보 $a$에서 예산으로 건설 가능한 동시수용량
- $OD(G^{route})$: 수도권 상태 확장 경로 그래프로 계산한 시간·일반화비용
- `Allocate`: 수요·용량·접근·이용자격 제약을 지키는 배분 솔버
- $J=(U,CVaR_{0.9},Z,\bar G,Cost)$: 형평성 우선 목적벡터

이 정의에서 GNN은 후보의 공간적 가치를 학습해 계산을 가속하지만, 경로·법규·예산·용량·수요 보전과 최종 정책 순위는 검증 가능한 솔버가 책임진다. 이 분리가 WelfareMap AI의 정확성, 설명 가능성, 보상 해킹 저항성을 보장하는 핵심 설계다.
