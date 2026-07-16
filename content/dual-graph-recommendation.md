## 권고안: 물리 격자 그래프 + 경로 상태 그래프의 이중 구조

핵심은 “100m 격자 하나 = 하나의 물리 노드” 원칙을 유지하면서도, 환승 비용처럼 이전 이동수단에 의존하는 비용은 별도의 상태 확장 라우팅 그래프에서 계산하는 것이다. 격자 노드만으로 환승을 표현하면 노선이 바뀌어도 패널티가 누락되거나, 같은 격자 내 여러 정류장이 무료로 연결되는 문제가 생긴다.

### 1. GNN용 물리 그래프

시간대 \(t\)별 멀티릴레이션 유향 멀티그래프로 구성한다.

\[
G_t=(V,E^{walk},E^{bus}_t,E^{subway}_t)
\]

- \(V\): 유효한 모든 100m 격자
- 동일한 두 격자 사이에 버스 노선별로 여러 간선 허용
- GNN은 물리 격자 임베딩을 만들고, 정책 헤드는 각 격자의 신규 시설 입지 점수를 출력
- 노선·방향 정보는 간선을 합쳐 없애지 않고 `route_id`, `direction_id`로 보존

#### 노드 특징

| 분류 | 예시 특징 |
|---|---|
| 수요 | `elderly_population`, 시간대별 `estimated_demand` |
| 기존 공급 | `facility_count`, `capacity_sum`, 현재 단계의 `added_capacity` |
| 교통 접근성 | 버스 정류장 수, 지하철역 수, 운행 노선 수, 시간대별 운행 노선 수 |
| 기초 사각지대 | 현재 시설까지 최소 일반화 비용, 15/30분 내 도달 가능 수용량 |
| 공간 | 좌표 정규화값 또는 Fourier 위치 인코딩, 경계 격자 여부 |
| 상태 | 유효 격자, 후보지 가능 여부, 이미 선택된 위치 여부 |
| 결측 | 각 주요 특징별 missing indicator |

최소 권장 벡터는 다음과 같다.

\[
x_{i,t}=[
\log(1+P_i),
\log(1+D_{i,t}),
\log(1+C_i),
F_i,
B_i,S_i,R^{bus}_{i,t},R^{sub}_{i,t},
A^{15}_{i,t},A^{30}_{i,t},
g^{nearest}_{i,t},
pos_i,
m_i
]
\]

- \(P_i\): 노인 인구 원자료
- \(D_{i,t}=P_i\rho_t\): 시간대별 예상 이용 수요
- \(C_i\): 격자 내 전체 시설 수용량 합
- \(A^{k}_{i,t}\): 일반화 비용 \(k\)분 이내 현재 시설 수용량
- \(g^{nearest}_{i,t}\): 현재 가장 가까운 시설까지의 일반화 비용

시간대별 이용률 \(\rho_t\)가 실측되지 않았다면 하나의 임의값으로 고정하지 말고 여러 수요 시나리오로 학습·평가하는 것이 안전하다.

### 2. 간선 설계

#### 도보 간선

- 기본 8방향 인접 격자 연결
- 거리: 직교 100m, 대각 약 141.4m
- 고령자 보행 속도로 이동시간 계산
- 경사·횡단보도·보행 안전 데이터가 없다면 균일 비용을 쓰되 결측 플래그 기록
- 교통수단이 있는 격자에서도 절대 제거하지 않음

특징 예:

```text
[distance_m, walk_time_min, slope, crossing_count,
 accessibility_score, missing_flags]
```

#### 버스·지하철 승차 간선

노선의 연속 정차 격자를 방향별로 연결한다. 동일 격자쌍도 노선이 다르면 별도 간선이다.

```text
[distance_m, in_vehicle_time,
 headway, expected_wait,
 reliability, seat_probability,
 service_active]
```

별도 범주형 값:

```text
route_id, direction_id, mode_id
```

운행하지 않는 시간대의 간선을 특징값 0으로 두면 “비용 0인 무료 간선”으로 오인할 수 있으므로 반드시 `edge_active=false`로 마스킹해야 한다.

정류장 위치만 있고 노선 순서·방향·배차간격·구간 운행시간이 없다면 정확한 대중교통·환승 모델은 만들 수 없다. 이 경우 정류장 수는 노드 특징으로만 쓰고, 운행 간선은 보수적인 추정치와 결측 플래그를 사용해야 한다.

### 3. 환승을 위한 상태 확장 라우팅 그래프

수요 배분 단계에서는 다음 상태를 사용한다.

\[
s=(grid,\ status,\ current/last\ service)
\]

예:

- `(i, OFF, NONE)`: 아직 교통수단을 타지 않은 상태
- `(i, ON_BUS, route_12)`
- `(i, ON_SUBWAY, line_2)`
- `(i, OFF, route_12)`: 하차했지만 직전 노선을 기억하는 상태

상태 전이는 다음과 같다.

```text
도보:
(i, OFF, last) → (j, OFF, last)

최초 승차:
(i, OFF, NONE) → (i, ON, route)

주행:
(i, ON, route) → (j, ON, route)

하차:
(i, ON, route) → (i, OFF, route)

환승:
(i, OFF, old_route) → (i, ON, new_route)
```

하차 후에도 `last_route`를 유지해야, 잠시 걷고 다른 정류장에서 승차하여 환승 패널티를 회피하는 경로를 막을 수 있다. 이 그래프는 GNN 물리 노드를 복제하는 것이 아니라 최단경로·수요 배분 계산에서만 사용하는 희소 상태 그래프다.

### 4. 일반화 이동비용과 보상 해킹 방지

경로 비용은 모든 항이 음수가 아닌 일반화 비용으로 정의한다.

\[
C(p)=
\beta_wT_{walk}
+\beta_qT_{wait}
+\sum_e T^{ride}_e
\left[
p^{seat}_e\beta_{seat}
+(1-p^{seat}_e)\beta_{stand}
\right]
+\kappa_{tr}N_{transfer}
+\kappa_{board}N_{board}
\]

제약:

\[
0<\beta_{seat}<\beta_{stand}\leq\beta_w,\qquad
\kappa_{tr}>0
\]

즉, 앉아서 이동하는 편안함은 승차시간의 체감 비용을 낮추는 방식으로 표현한다. 승차 자체에 양의 보상을 주거나 승차시간을 음수 비용으로 만들면 버스·지하철을 반복 탑승하는 순환 경로가 유리해진다.

필수 방어 규칙:

- 출발지에서 시설까지 순수 도보 경로를 항상 후보에 포함
- 대중교통 이용을 강제하지 않고 모든 경로 중 최소 일반화 비용 선택
- 승차·탑승 횟수에 양의 보상 금지
- 모든 이동·대기·환승 비용에 양의 하한 적용
- 같은 상태 `(grid, mode, route)`를 반복하는 경로 제거 또는 dominance pruning
- 최대 환승 수를 현실적인 상한으로 제한
- 서로 다른 노선 간선을 `min travel time`으로 합치지 않음
- 같은 격자 내 환승도 실제 환승 보행시간 또는 보수적 하한 적용
- softmin을 사용한다면 명백히 열등한 순환·우회 경로를 먼저 제거
- 최단거리 기준은 교통 이용 횟수가 아니라 일반화 비용

이 설계에서는 가까운 시설은 도보가 자동으로 선택되고, 먼 시설은 낮은 승차 체감비용 때문에 대중교통 경로가 선택될 수 있다.

### 5. 시간대 설계

운행과 수요가 다른 시간대를 별도 스냅샷으로 둔다.

- 평일 출근·오전 이용 시간
- 평일 비첨두
- 평일 저녁
- 주말 또는 휴일

실제 데이터가 있으면 고정된 1시간 단위 또는 서비스 변경 시점 기준으로 구성한다. 시간 특징에는 다음을 추가한다.

```text
sin(2π·hour/24), cos(2π·hour/24),
day_type, peak_flag
```

시설 수용량이 일일 수용량인지 동시 수용량인지 구분해야 한다. 같은 노인을 여러 시간대 수요로 중복 합산하지 말고, 시간대별 기대값·최악값·상위 분위수 등 명시된 집계 규칙으로 최종 보상을 계산한다.

### 6. 정규화

- 인구·수요·수용량·정류장 수: `log1p` 후 학습 세트의 median/IQR 또는 mean/std
- 시간·거리: 60분, 1km처럼 고정된 물리 단위로 스케일
- 좌표: 분석 영역 기준 `[-1,1]` 또는 Fourier encoding
- 확률·비율: `[0,1]`로 clip
- 범주형 `route_id`, `mode_id`: embedding 사용, 수치 정규화 금지
- 결측값: 0 대체와 missing indicator를 함께 사용
- 검증·테스트 지역이나 신규 시설 배치 결과를 이용해 정규화 통계를 계산하지 않음

수요 배분과 수용량 제약에는 정규화값이 아니라 원래의 정수/실수 값을 사용해야 한다. 정규화된 수용량으로 min-cost flow를 수행하면 반올림이나 스케일 오차 때문에 실제 수용량을 초과할 수 있다.

### 7. 마스킹

```text
node_valid_mask[N]
candidate_mask[N]
demand_mask[T,N]
facility_mask[N]
edge_active_mask[relation,T,E]
time_mask[T]
selected_mask[step,N]
```

후보지 마스크 권장식:

```text
candidate_mask =
    node_valid
  & land_or_policy_feasible
  & budget_feasible
  & min_spacing_satisfied
  & ~already_selected
```

주의점:

- 인구가 0인 격자도 주변 수요를 서비스할 수 있으므로 후보에서 자동 제외하지 않음
- 교통 정류장이 없는 격자도 도보 접근이 가능하므로 제외하지 않음
- 저인구 격자를 마스킹하면 외곽 사각지대를 구조적으로 무시할 수 있음
- 기존 시설과의 동일 격자 입지를 허용할지는 정책으로 명시
- 운행 중단 간선은 비용 0이 아니라 비활성 마스크 처리
- 수요가 없는 노드도 메시지 전달용 공간 노드로 유지

### 8. 구현 가능한 텐서 스키마

```python
# 물리 격자
x_static:          FloatTensor[N, F_static]
x_time:            FloatTensor[T, N, F_dynamic]
pos:               FloatTensor[N, 2]

population_raw:    FloatTensor[N]
demand_raw:        FloatTensor[T, N]
capacity_raw:      FloatTensor[N]
facility_count:    LongTensor[N]

node_valid_mask:   BoolTensor[N]
candidate_mask:    BoolTensor[N]
demand_mask:       BoolTensor[T, N]
selected_mask:     BoolTensor[K, N]       # 순차 배치 시
time_mask:         BoolTensor[T]

# relation r ∈ {walk, bus, subway}
edge_index[r]:     LongTensor[2, E_r]
edge_attr[r]:      FloatTensor[T, E_r, F_edge_r]
edge_active[r]:    BoolTensor[T, E_r]
route_id[r]:       LongTensor[E_r]        # walk는 sentinel
direction_id[r]:   LongTensor[E_r]
mode_id[r]:        LongTensor[E_r]

# 상태 확장 라우팅 그래프
state_grid_id:     LongTensor[S]
state_status:      LongTensor[S]
state_service_id:  LongTensor[S]

route_edge_index:  LongTensor[2, E_state]
route_edge_cost:   FloatTensor[T, E_state]
route_edge_type:   LongTensor[E_state]
route_edge_active: BoolTensor[T, E_state]

# 정책 출력
location_logits:   FloatTensor[B, N]
```

정책 출력 직전에:

```python
location_logits[~candidate_mask] = -inf
```

GNN은 relation별 edge-conditioned message passing 또는 R-GAT을 사용하고, 시간축은 temporal attention/GRU로 합칠 수 있다. 후보 점수는 `cell_embedding + global_graph_embedding + candidate_features`로 계산하는 구성이 적합하다.

마지막으로 입력에는 현재 상태에서 계산한 접근성만 넣고, 신규 시설을 배치한 뒤의 배분량·보상·잔여 수용량을 넣어서는 안 된다. 이는 후보 위치 정답을 직접 노출하는 target leakage가 된다.