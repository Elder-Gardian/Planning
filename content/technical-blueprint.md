# WelfareMap AI

## 기술 청사진

### 노인 복지시설 계획을 위한 그래프 신경망 및 강화학습 아키텍처

---

## 1. 시스템 목표

시스템은 지리공간·인구·교통·복지시설 데이터를 입력받아 다음을 산출한다.

- 100m 격자별 복지 접근성 점수
- 격자별 추정 미충족 노인 인구
- 신규 복지시설 추천 입지
- 추천 시설 수용 규모
- 예상 커버리지 개선 효과
- 예상 이동 시간 변화
- 비용 및 형평성 지표

핵심 기술 아키텍처는 다음과 같다.

```
공공·행정 원천 데이터
        ↓
   공간 데이터 처리
        ↓
     교통 네트워크
        ↓
   격자 그래프 데이터셋
        ↓
     GNN 인코더
        ↓
 강화학습 입지 정책
        ↓
 시설 입지 및 규모 결정
        ↓
 수용 제약 기반 수요 배정
        ↓
   보상 및 평가 지표
```

---

## 2. 모델링 전략

핵심 모델은 다음으로 구성된 하이브리드 시스템이다.

1. 공간·교통 표현을 위한 그래프 신경망(GNN)
2. 시설 입지를 결정하는 강화학습 정책
3. 평가를 위한 수용 제약 기반 배정 알고리즘
4. 후처리를 위한 선택적 지역 탐색(local search) 알고리즘

GNN은 인접 격자 및 대중교통으로 연결된 격자 간의 관계를 학습한다.

강화학습 에이전트는 시설의 입지와 수용 규모를 선택한다.

배정 알고리즘은 제안된 시설이 수용 규모와 이동 제약 아래에서 실제로 인구를 감당할 수 있는지를 판정한다.

---

## 3. 공간 단위

대상 지역은 100m × 100m 격자로 분할한다.

각 격자는 다음 역할을 겸한다.

- 공간 분석 단위
- 수요 단위
- 그래프 노드
- 잠재적 시설 후보 입지

각 격자에는 고유 식별자가 부여된다.

예시:

```json
{
  "grid_id": "G10293",
  "centroid_latitude": 37.6542,
  "centroid_longitude": 127.0618,
  "elderly_population": 84
}
```

---

## 4. 데이터 스키마

### 4.1 격자 테이블

```
grid_id
geometry
centroid
elderly_population          (노인 인구)
estimated_demand            (추정 수요)
vulnerability_score         (취약성 점수)
installation_allowed        (설치 가능 여부)
land_cost                   (지가)
pedestrian_barrier_score    (보행 장애 점수)
```

### 4.2 복지시설 테이블

```
facility_id
facility_type               (시설 유형)
geometry
daily_capacity              (일일 수용 규모)
current_usage               (현재 이용량)
available_capacity          (가용 수용 여력)
service_type                (서비스 유형)
operating_hours             (운영 시간)
```

### 4.3 버스 정류장 테이블

```
stop_id
geometry
route_ids                   (경유 노선)
average_waiting_time        (평균 대기 시간)
accessible_vehicle_ratio    (저상버스 등 접근 가능 차량 비율)
```

### 4.4 지하철역 테이블

```
station_id
geometry
line_ids                    (노선)
transfer_available          (환승 가능 여부)
elevator_available          (엘리베이터 유무)
```

### 4.5 교통 엣지 테이블

```
source_id
target_id
mode                        (이동 수단)
travel_time                 (이동 시간)
walking_time                (도보 시간)
waiting_time                (대기 시간)
number_of_transfers         (환승 횟수)
distance                    (거리)
barrier_score               (장애 점수)
```

---

## 5. 복지 수요 추정

### 5.1 초기 수요

초기 모델에서는 다음과 같이 정의한다.

$$
D_i = P_i
$$

여기서:

- $D_i$ : 격자 $i$의 복지 수요
- $P_i$ : 격자 $i$의 노인 인구

이는 확정된 복지 서비스 필요가 아니라 **잠재 수요**를 나타낸다.

### 5.2 취약성 가중 수요

추가 인구통계 데이터가 있을 때:

$$
D_i = P_i \, q_i
$$

여기서 $q_i$는 추정된 복지 서비스 필요율이다.

간단한 규칙 기반 추정은 다음과 같다.

$$
q_i = w_1 r_i^{75+} + w_2 r_i^{\text{alone}} + w_3 r_i^{\text{lowincome}} + w_4 r_i^{\text{disabled}}
$$

(각각 75세 이상 비율, 독거 비율, 저소득 비율, 장애 비율)

### 5.3 머신러닝 수요 모델

과거 이용 실적 데이터가 확보되면, 별도의 모델로 수요를 추정할 수 있다.

$$
\hat{D}_i = f_\phi(X_i)
$$

권장 초기 모델:

- LightGBM
- CatBoost
- 일반화 가법 모델(GAM)
- 랜덤 포레스트

가능한 학습 목표(target):

- 월별 복지관 방문 수
- 대기자 수
- 서비스 신청 건수
- 반려·미배정 신청 건수

---

## 6. 교통 비용 모델링

격자 $i$에서 목적지 $j$까지의 일반화 이동 비용은 다음과 같다.

$$
T_{ij} = T_{ij}^{\text{walk}} + T_{ij}^{\text{wait}} + T_{ij}^{\text{ride}} + \alpha \, N_{ij}^{\text{transfer}} + \beta \, B_{ij}
$$

여기서:

- $T_{ij}^{\text{walk}}$ : 도보 시간
- $T_{ij}^{\text{wait}}$ : 대기 시간
- $T_{ij}^{\text{ride}}$ : 차내 이동 시간
- $N_{ij}^{\text{transfer}}$ : 환승 횟수
- $B_{ij}$ : 접근 장애 점수
- $\alpha$ : 환승 페널티
- $\beta$ : 장애 페널티

노인 접근성을 다룰 때는 일반 경로 탐색보다 도보 및 환승 페널티를 더 크게 설정해야 한다.

---

## 7. 기종점(OD) 행렬

격자와 복지시설 사이에 기종점 행렬을 생성한다.

$$
M_{ij} = T(i, j)
$$

시설이 합리적으로 접근 가능하다고 판단될 때에만 엣지를 유지한다.

$$
(i, j) \in E_{GF} \quad \text{if} \quad T_{ij} \le T_{\max}
$$

가능한 임계값:

- 15분
- 20분
- 30분

민감도 분석 시 여러 임계값을 시험해야 한다.

---

## 8. 그래프 구성

### 8.1 그래프 정의

$$
G = (V, E, X, E_f)
$$

여기서:

- $V$ : 격자 노드
- $E$ : 교통 기반 엣지
- $X$ : 노드 특징 행렬
- $E_f$ : 엣지 특징 행렬

### 8.2 노드 특징

격자 $i$에 대해:

$$
x_i = [\, P_i,\ D_i,\ A_i,\ R_i,\ C_i,\ V_i,\ B_i,\ L_i,\ F_i \,]
$$

여기서:

- $P_i$ : 노인 인구
- $D_i$ : 추정 수요
- $A_i$ : 현재 복지 접근성
- $R_i$ : 교통 접근성
- $C_i$ : 인근 가용 복지 수용 여력
- $V_i$ : 취약성 점수
- $B_i$ : 보행 장애 점수
- $L_i$ : 설치 가능성
- $F_i$ : 추정 설치 비용

### 8.3 엣지 특징

엣지 $(i, j)$에 대해:

$$
e_{ij} = [\, t_{ij}^{\text{walk}},\ t_{ij}^{\text{transit}},\ n_{ij}^{\text{transfer}},\ d_{ij},\ b_{ij} \,]
$$

### 8.4 그래프 연결 방식 옵션

**공간 인접 그래프**

이웃한 격자 셀을 연결한다.

- 4-이웃
- 8-이웃

**이동시간 그래프**

임계값 내에 도달 가능한 격자끼리 연결한다.

$$
(i, j) \in E \quad \text{if} \quad T_{ij} < \tau
$$

이것을 초기 권장 구조로 삼는다.

**이종(heterogeneous) 그래프**

노드 유형:

- 격자
- 버스 정류장
- 지하철역
- 복지시설

엣지 유형:

- 격자–격자 도보
- 격자–정류장 접근
- 정류장–정류장 버스 이동
- 역–역 지하철 이동
- 격자–시설 접근

이 구조는 표현력이 더 크지만, 후속 단계로 미뤄두는 것이 좋다.

---

## 9. 현재 접근성 특징

시설 추천에 앞서 기준선 접근성 특징을 계산해야 한다.

### 9.1 최근접 시설 이동 시간

$$
A_i^{\text{nearest}} = \min_j T_{ij}
$$

### 9.2 수용 규모 가중 접근성

$$
A_i = \sum_j \frac{C_j \, f(T_{ij})}{\sum_k D_k \, f(T_{kj})}
$$

여기서 $f(T)$는 이동시간 감쇠 함수이다.

예시:

$$
f(T) = e^{-\gamma T}
$$

### 9.3 격자 인근 가용 수용 여력

$$
C_i^{\text{near}} = \sum_j C_j^{\text{available}} \, f(T_{ij})
$$

이 값들은 GNN 노드 특징으로 포함할 수 있다.

---

## 10. GNN 인코더

### 10.1 초기 임베딩

$$
h_i^{(0)} = \operatorname{MLP}(x_i)
$$

### 10.2 메시지 전달

$$
m_i^{(l)} = \sum_{j \in \mathcal{N}(i)} \alpha_{ij}^{(l)} \, W_v h_j^{(l)}
$$

어텐션 계수는 노드 및 엣지 특징에 의존할 수 있다.

$$
\alpha_{ij} = \operatorname{softmax}_j \left( a \left[ W_q h_i \,\Vert\, W_k h_j \,\Vert\, W_e e_{ij} \right] \right)
$$

### 10.3 노드 갱신

$$
h_i^{(l+1)} = \operatorname{LayerNorm}\left( h_i^{(l)} + \operatorname{MLP}\left( m_i^{(l)} \right) \right)
$$

### 10.4 권장 모델

초기 후보:

- 그래프 어텐션 네트워크(GAT)
- 엣지 특징을 반영한 GraphSAGE
- TransformerConv
- 그래프 트랜스포머

단순 GCN은 베이스라인으로 유지한다.

---

## 11. 강화학습 환경

### 11.1 상태(State)

스텝 $t$에서 상태는 다음을 포함한다.

$$
s_t = (\, G,\ D_t,\ C_t,\ S_t,\ B_t,\ K_t \,)
$$

여기서:

- $G$ : 격자 그래프
- $D_t$ : 남은 미충족 수요
- $C_t$ : 현재 시설 수용 규모 상태
- $S_t$ : 선택된 시설 집합
- $B_t$ : 남은 예산
- $K_t$ : 남은 설치 가능 횟수

### 11.2 행동(Action)

기본 행동은 다음과 같다.

$$
a_t = (i_t,\ c_t)
$$

여기서:

- $i_t$ : 선택된 격자
- $c_t$ : 선택된 시설 수용 규모

수용 규모는 이산적 선택지에서 고를 수 있다.

- 50명
- 100명
- 200명

### 11.3 확장 행동

후속 버전에서는 다음을 포함할 수 있다.

```
BUILD_NEW          (신설)
EXPAND_EXISTING    (기존 확충)
MOVE_FACILITY      (시설 이전)
REMOVE_FACILITY    (시설 폐지)
STOP               (종료)
```

### 11.4 행동 마스킹

유효하지 않은 행동은 반드시 마스킹해야 한다.

다음의 경우 격자는 유효하지 않다.

- 건립이 금지된 경우
- 이미 선택된 격자인 경우
- 필요한 예산이 남은 예산을 초과하는 경우
- 다른 시설과의 최소 이격 거리를 위반하는 경우
- 부지 여건이 불충분한 경우

$$
p_i = \operatorname{softmax}(s_i + \operatorname{mask}_i)
$$

여기서 유효하지 않은 위치에는 큰 음수 마스크 값이 부여된다.

---

## 12. 입지 정책

### 12.1 입지 헤드(Location Head)

$$
s_i^{\text{location}} = W_l h_i
$$

$$
\pi_\theta(i_t \mid s_t) = \operatorname{softmax}(s_i^{\text{location}} + \operatorname{mask}_i)
$$

### 12.2 수용 규모 헤드(Capacity Head)

격자 $i_t$를 선택한 후:

$$
\pi_\theta(c_t \mid i_t, s_t) = \operatorname{softmax}\left( \operatorname{MLP}_c(h_{i_t}) \right)
$$

### 12.3 가치 헤드(Value Head)

그래프 수준 임베딩을 계산한다.

$$
h_G = \operatorname{AttentionPool}\left( \{ h_i \} \right)
$$

크리틱은 다음을 추정한다.

$$
V_\psi(s_t) = \operatorname{MLP}_v(h_G)
$$

---

## 13. 강화학습 알고리즘

**권장 초기 알고리즘**

근접 정책 최적화(Proximal Policy Optimization, PPO)

선정 이유:

- 안정적인 정책 갱신
- 마스킹된 범주형 행동과의 호환성
- 순차적 의사결정 지원
- 직관적인 액터-크리틱 구현

**대안 알고리즘**

- REINFORCE
- A2C
- DQN
- 포인터 네트워크 정책
- 완화된 연속 결정을 위한 Soft Actor-Critic
- 신경망 유도 몬테카를로 트리 탐색(MCTS)

---

## 14. 수용 제약 기반 수요 배정

정책이 시설 배치를 생성한 후, 수요를 시설에 배정한다.

### 14.1 결정 변수

$$
x_{ij} \ge 0
$$

격자 $i$에서 시설 $j$로 배정된 인원 수.

$$
u_i \ge 0
$$

격자 $i$의 미충족 수요.

### 14.2 수요 제약

$$
\sum_j x_{ij} + u_i = D_i
$$

### 14.3 수용 규모 제약

$$
\sum_i x_{ij} \le C_j
$$

### 14.4 접근성 제약

$$
x_{ij} = 0 \quad \text{if} \quad T_{ij} > T_{\max}
$$

### 14.5 배정 목적 함수

$$
\min \ \lambda_u \sum_i v_i u_i + \lambda_t \sum_{i,j} T_{ij} x_{ij}
$$

다음 방법으로 풀 수 있다.

- 최소 비용 흐름(minimum-cost flow)
- 선형 계획법(LP)
- 빠른 근사를 위한 탐욕적 배정
- OR-Tools
- Gurobi
- NetworkX 최소 비용 흐름

---

## 15. 보상 함수

일반적인 보상 함수는 다음과 같다.

$$
R = -\lambda_1 U - \lambda_2 T - \lambda_3 C - \lambda_4 I - \lambda_5 P
$$

여기서:

- $U$ : 총 미충족 수요
- $T$ : 총 이동 비용
- $C$ : 설치 비용
- $I$ : 지역 간 불균형
- $P$ : 제약 위반 페널티

### 15.1 미충족 수요

$$
U = \sum_i u_i
$$

### 15.2 이동 비용

$$
T = \sum_{i,j} T_{ij} x_{ij}
$$

### 15.3 설치 비용

$$
C = \sum_k \left( F_k y_k + c_k s_k \right)
$$

### 15.4 형평성 페널티

가능한 정의:

$$
I = \operatorname{Var}\left( \operatorname{CoverageRatio}_i \right)
$$

또는:

$$
I = 1 - \min_i \operatorname{CoverageRatio}_i
$$

또는 격자별 커버리지에 대한 지니 계수.

### 15.5 증분 보상

보다 안정적인 스텝 보상은 다음과 같다.

$$
r_t = (U_{t-1} - U_t) - \alpha (C_t - C_{t-1}) - \beta (T_t - T_{t-1})
$$

이는 각 시설 결정 이후 미충족 수요의 감소량을 보상한다.

---

## 16. 에피소드 구조

**초기화(Reset)**

각 에피소드 시작 시:

- 지역 그래프 로드
- 수요 조건 샘플링
- 기존 수용 규모 조건 샘플링
- 예산 설정
- 설치 가능한 시설 수 설정

**스텝(Step)**

각 스텝에서:

1. 현재 그래프 인코딩
2. 시설 입지 선택
3. 시설 수용 규모 선택
4. 상태 갱신
5. 수요 배정 실행
6. 보상 계산

**종료(Termination)**

에피소드는 다음 경우 종료된다.

- 시설 개수 한도 도달
- 예산 소진
- 유효한 후보가 남지 않음
- 에이전트가 STOP 선택

---

## 17. 학습 데이터 생성

### 17.1 시나리오 무작위화

다음을 변화시켜 다수의 학습 인스턴스를 생성한다.

- 노인 인구 분포
- 추정 복지 수요
- 기존 시설 위치
- 기존 수용 규모
- 시설 건립 비용
- 총예산
- 대중교통 이동 시간
- 버스 대기 시간
- 도로 단절
- 후보 시설 부지

### 17.2 지역 부분 그래프

다양한 크기의 부분 그래프를 생성한다.

- 10 × 10 격자
- 20 × 20 격자
- 30 × 30 격자
- 행정동 부분 그래프
- 교통 집수(catchment) 구역

### 17.3 커리큘럼 학습

점진적으로 학습한다.

1. 작은 그래프에서 시설 1개
2. 작은 그래프에서 시설 여러 개
3. 수용 규모 결정을 포함한 시설 여러 개
4. 대규모 지역 그래프
5. 동적 교통 시나리오

### 17.4 솔버 기반 사전학습

작은 인스턴스에 대해서는 다음으로 전문가 해를 생성한다.

- 혼합정수 선형계획법(MILP)
- 탐욕적 지역 탐색
- 유전 알고리즘
- 시뮬레이티드 어닐링

정책을 먼저 모방학습으로 학습시킬 수 있다.

$$
\mathcal{L}_{IL} = -\sum_t \log \pi_\theta(a_t^* \mid s_t)
$$

사전학습 후, 모델을 강화학습으로 미세 조정한다.

---

## 18. 지역 탐색 후처리

RL 출력은 지역 탐색(local search)으로 개선할 수 있다.

**교환(Swap) 연산자**

선택된 시설 하나를 제거하고 다른 후보를 추가한다.

$$
S' = S - \{i\} + \{j\}
$$

다음 조건에서 교환을 수용한다.

$$
J(S') < J(S)
$$

가능한 연산자:

- 입지 교환
- 수용 규모 증가
- 수용 규모 감소
- 두 소형 시설 병합
- 하나의 대형 시설 분할

이로써 신경망–최적화 하이브리드 시스템이 완성된다.

---

## 19. 베이스라인 모델

제안 모델은 다음과 비교되어야 한다.

**무작위 배치**

유효한 후보 격자를 무작위로 선택한다.

**인구 밀도 순위**

노인 인구가 가장 많은 격자를 선택한다.

**접근성 결핍 순위**

현재 이동 시간이 가장 긴 격자를 선택한다.

**탐욕적 최대 커버리지**

각 스텝에서 추가 수요를 가장 많이 커버하는 위치를 선택한다.

**K-메도이드(K-Medoids)**

수요 지점을 군집화하고 메도이드에 시설을 배치한다.

**유전 알고리즘**

시설 집합을 염색체로 표현한다.

**혼합정수 계획법(MILP)**

소규모 인스턴스에 대한 정확 또는 준정확 벤치마크로 사용한다.

**CNN 베이스라인**

공간 특징을 래스터 채널로 표현하고 시설 적합도를 예측한다.

**GNN 지도학습 베이스라인**

솔버가 생성한 의사 라벨로 GNN을 학습한다.

---

## 20. 평가 지표

**총 미충족 인구**

$$
U = \sum_i u_i
$$

**커버리지율**

$$
\text{Coverage} = 1 - \frac{\sum_i u_i}{\sum_i D_i}
$$

**평균 이동 시간**

$$
\text{MeanTravelTime} = \frac{\sum_{i,j} T_{ij} x_{ij}}{\sum_{i,j} x_{ij}}
$$

**90퍼센타일 이동 시간**

극단적 접근성 불이익을 측정하는 데 사용한다.

**취약성 가중 커버리지**

$$
\text{WeightedCoverage} = 1 - \frac{\sum_i v_i u_i}{\sum_i v_i D_i}
$$

**지역 커버리지 분산**

$$
\text{EquityGap} = \operatorname{Std}\left( \text{CoverageRatio}_i \right)
$$

**비용 효율**

$$
\text{CostEfficiency} = \frac{\text{추가 수혜 인구}}{\text{설치 비용}}
$$

**최적성 격차(Optimality Gap)**

소규모 인스턴스에 대해:

$$
\text{OptimalityGap} = \frac{J_{\text{model}} - J_{\text{optimal}}}{|J_{\text{optimal}}|}
$$

**추론 시간**

다음을 측정한다.

- 그래프 인코딩 시간
- 입지 생성 시간
- 배정 시간
- 전체 시나리오 평가 시간

---

## 21. 실험 설계

**실험 1: 그래프 vs 래스터 표현**

비교 대상:

- CNN
- GCN
- GAT
- 그래프 트랜스포머

**실험 2: RL vs 휴리스틱 배치**

비교 대상:

- 인구 순위
- 탐욕적 배치
- 유전 알고리즘
- PPO 정책

**실험 3: 보상 요소 제거(Ablation)**

한 번에 하나씩 보상 요소를 제거한다.

- 형평성 페널티 제거
- 이동시간 페널티 제거
- 비용 페널티 제거
- 취약성 가중치 제거

**실험 4: 엣지 특징 제거**

비교 대상:

- 공간 인접만
- 이동 시간만
- 이동 시간 + 환승
- 전체 교통 및 장애 특징

**실험 5: 일반화**

일부 지역으로 학습하고, 학습에 사용하지 않은 지역으로 테스트한다.

**실험 6: 수용 규모 민감도**

여러 시설 규모를 평가한다.

- 50
- 100
- 200

**실험 7: 이동시간 임계값 민감도**

다음을 평가한다.

- 15분
- 20분
- 30분

---

## 22. 디퓨전 확장

후속 버전은 조건부 그래프 디퓨전 모델을 사용하여 여러 개의 고품질 시설 배치안을 생성할 수 있다.

**시설 선택 벡터**

$$
y_i =
\begin{cases}
1 & \text{격자 } i \text{에 시설 설치} \\
0 & \text{그 외}
\end{cases}
$$

**조건부 생성**

$$
p_\theta(Y \mid G, X, B, K, O)
$$

여기서:

- $B$ : 예산
- $K$ : 시설 개수
- $O$ : 정책 목표

가능한 목표:

- 최대 커버리지
- 최소 이동 시간
- 최소 비용
- 최대 형평성

디퓨전 모델은 최종 타당성 평가자가 아니라 **후보 생성기**로 사용해야 한다.

생성된 배치안은 반드시 다음 과정을 거쳐야 한다.

1. 제약 투영(constraint projection)
2. 수요 배정
3. 지역 탐색
4. 최종 순위 결정

---

## 23. 백엔드 아키텍처

**데이터 계층**

- PostgreSQL
- PostGIS
- 그래프 데이터셋용 오브젝트 스토리지

**전처리 계층**

- GeoPandas
- Shapely
- OSMnx
- GTFS 파서
- NetworkX

**머신러닝 계층**

- PyTorch
- PyTorch Geometric
- Stable-Baselines3 또는 커스텀 PPO
- (필요 시) 분산 학습용 Ray RLlib

**최적화 계층**

- OR-Tools
- Gurobi
- NetworkX 최소 비용 흐름

**API 계층**

- FastAPI
- Pydantic
- 시나리오 캐싱용 Redis

---

## 24. API 설계 예시

**현재 접근성 분석**

`POST /analysis/current`

요청:

```json
{
  "region_id": "seoul-nowon",
  "service_type": "senior_welfare",
  "max_travel_time": 30
}
```

응답:

```json
{
  "total_demand": 18420,
  "covered_population": 14630,
  "uncovered_population": 3790,
  "coverage_ratio": 0.794,
  "average_travel_time": 21.4
}
```

**격자 단위 사각지대**

`GET /analysis/grids`

응답:

```json
[
  {
    "grid_id": "G10293",
    "elderly_population": 84,
    "estimated_demand": 52,
    "covered_population": 21,
    "uncovered_population": 31,
    "coverage_ratio": 0.404,
    "blind_spot_score": 0.81
  }
]
```

**시설 추천**

`POST /recommendations/facilities`

요청:

```json
{
  "region_id": "seoul-nowon",
  "budget": 3000000000,
  "facility_count": 2,
  "capacity_options": [50, 100, 200],
  "objective": "equity",
  "max_travel_time": 30
}
```

응답:

```json
{
  "recommendations": [
    {
      "grid_id": "G21045",
      "capacity": 100,
      "estimated_cost": 1300000000,
      "additional_coverage": 87,
      "affected_grids": 14
    }
  ],
  "before": {
    "coverage_ratio": 0.794,
    "uncovered_population": 3790
  },
  "after": {
    "coverage_ratio": 0.866,
    "uncovered_population": 2464
  }
}
```

---

## 25. 구현 로드맵

**1단계: 데이터 파이프라인**

- 100m 격자 생성
- 노인 인구 집계
- 복지시설 수집
- 시설 수용 규모 추정
- 도로·대중교통 그래프 구축
- 격자–시설 이동 시간 계산

**2단계: 기계적 베이스라인**

- 수요 배정 구현
- 현재 커버리지 계산
- 탐욕적 시설 배치 구현
- 사각지대 시각화

**3단계: 그래프 모델**

- 그래프 데이터셋 구성
- GCN 베이스라인 구현
- GAT 또는 그래프 트랜스포머 구현
- 노드 임베딩 검증

**4단계: 강화학습**

- Gym 호환 환경 구축
- 행동 마스킹 구현
- 수요 배정 연동
- PPO 구현
- 보상 스케일 안정화

**5단계: 평가**

- 휴리스틱과 비교
- 소규모 인스턴스에서 MILP와 비교
- 제거(ablation) 연구 수행
- 미학습 지역 테스트

**6단계: 서비스 통합**

- FastAPI 엔드포인트 구축
- 시나리오 관리 기능 구현
- 인터랙티브 지도 연동
- 추천 근거 설명 생성

**7단계: 고급 확장**

- 수요 예측 모델
- 기존 시설 확충 행동
- 이종 교통 그래프
- 조건부 그래프 디퓨전
- 시간대별 교통 분석

---

## 26. 권장 MVP 범위

초기 MVP는 다음을 포함해야 한다.

- 대상 지역 1곳
- 100m 격자 인구
- 버스·지하철 이동 시간
- 복지시설 위치
- 추정 시설 수용 규모
- 단일 복지 서비스 유형
- 50·100·200명의 시설 규모 선택지
- GAT 인코더
- PPO 입지 정책
- 최소 비용 수요 배정
- 복지 사각지대 시각화
- 설치 전후 시나리오 비교

MVP에서 제외할 사항:

- 실시간 교통
- 다중 복지 서비스 범주
- 상세 토지이용 타당성
- 이종 그래프 모델링
- 디퓨전 생성
- 전국 단위 일반화

---

## 27. 최종 기술 정의

제안 시스템은 다음과 같이 형식적으로 정의할 수 있다.

$$
\max_{\pi_\theta} \ \mathbb{E}_{\pi_\theta} \left[ -\lambda_1 U - \lambda_2 T - \lambda_3 C - \lambda_4 I \right]
$$

제약 조건:

$$
\sum_j x_{ij} + u_i = D_i
$$

$$
\sum_i x_{ij} \le C_j
$$

$$
x_{ij} = 0 \quad \text{if} \quad T_{ij} > T_{\max}
$$

$$
\sum_k \text{Cost}(i_k, c_k) \le B
$$

GNN이 공간 상태를 인코딩하고, 강화학습 정책이 시설의 입지와 수용 규모를 선택하며, 배정 알고리즘이 제안된 배치가 수용 규모 및 접근성 요건을 충족하는지를 평가한다.

이 아키텍처는 머신러닝을 의사결정 과정의 중심에 두면서도, 타당성·해석 가능성·정책 적합성을 함께 보존한다.