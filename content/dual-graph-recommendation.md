## 권고안: 100m 의사결정 그래프 + 상태 확장 경로 그래프

P0의 목표는 대상 자치구의 100m 격자별 **예상 동시 이용자**를 수요로 두고, 예산과 필지 규제를 만족하는 경로당 후보 한 곳을 선택하는 것이다. “100m 격자 하나 = GNN 노드 하나” 원칙은 유지하되, 환승처럼 이동 이력에 따라 달라지는 비용은 별도의 상태 확장 경로 그래프가 계산한다.

이 분리는 선택 사항이 아니다. 격자 그래프만으로 최단경로를 계산하면 같은 격자 안의 여러 정류장이 무료로 연결되거나, 하차한 뒤 조금 걸어서 다른 노선에 타는 방식으로 환승 패널티를 피할 수 있다. 반대로 정류장·역을 모두 GNN 노드로 만들면 사용자가 정한 공간 의사결정 단위와 모델의 행동 단위가 달라진다.

P0에서 GNN의 행동은 `후보 격자 1개 선택`뿐이다. 시설 면적과 동시수용량은 선택한 격자 안의 필지·사업유형·예산을 검토하는 계산기가 결정한다.

### 1. 두 그래프의 책임과 분석 경계

| 구성요소 | 책임 | 포함 범위 |
|---|---|---|
| 100m 물리 격자 그래프 | 수요·공급·접근성·후보지의 공간적 상호작용 인코딩 | 대상구와 경로 계산에 필요한 주변 격자 |
| 상태 확장 경로 그래프 | 도보·승차·대기·하차·환승을 포함한 최저 일반화비용 계산 | 수도권 전체 또는 시간 상한보다 넓은 네트워크 버퍼 |
| 필지·예산 계산기 | 후보별 건축 가능 면적·사업비·신규 동시수용량 산출 | 대상구 내부의 실제 필지·건물 |
| 형평성 배분 솔버 | 기존·신규 시설에 수요를 용량 내 배정하고 미수용 수요 계산 | 이용자격과 접근 상한을 만족하는 시설 |

행정경계는 역할별로 다르게 적용한다.

- 수요 origin은 대상 자치구에 둔다.
- 신규 시설 후보는 사업 예산의 관할 자치구에 둔다.
- 경로망은 자치구 경계에서 자르지 않는다.
- 기존 시설 destination은 시설별 이용자격을 만족할 때만 허용한다.
- 경계 밖 역·정류장은 destination이 아니어도 중간 경로 노드로 유지한다.

따라서 광운대역에서 석계역을 거쳐 6호선을 이용하는 경로는 허용된다. 노원에서 구로 같은 장거리 배정은 행정구역 hard ban이 아니라 실제 이동시간, 일반화비용 상한, 시설 이용자격으로 배제한다.

수도권 정적 기반망은 [KTDB 전국 GTFS](https://www.ktdb.go.kr/www/selectBbsNttView.do?bbsNo=2&key=45&nttNo=3785)를 사용하고, 서울 구간은 [서울 버스 노선 API](https://www.data.go.kr/data/15000193/openapi.do), [정류장 구간별 평균 운행시간](https://data.seoul.go.kr/dataList/OA-21217/S/1/datasetView.do), [서울교통공사 열차시각표](https://www.data.go.kr/data/15143847/openapi.do)로 갱신·검증한다.

### 2. GNN용 물리 격자 그래프

시간대와 수요 시나리오별 멀티릴레이션 유향 멀티그래프로 구성한다.

\[
G_{t,s}^{grid}=(V,E^{spatial},E^{walk},E^{bus}_{t},E^{rail}_{t},X_{t,s})
\]

- \(V\): 유효한 모든 100m 격자
- \(E^{spatial}\): 공간 문맥 전달을 위한 4방향 또는 8방향 인접 관계
- \(E^{walk}\): 실제 보행자도로망으로 연결된 격자 관계
- \(E^{bus},E^{rail}\): 노선·방향·정차순서를 보존한 대중교통 관계
- \(X_{t,s}\): 시간대 \(t\), 수요 시나리오 \(s\)의 노드 특징

동일 격자쌍 사이에 여러 노선 간선을 허용한다. 노선이 다르면 `route_id`, `direction_id`, `mode_id`를 보존하고 최소시간 하나로 합치지 않는다. 다만 **정확한 이동비용은 물리 그래프가 아니라 상태 확장 경로 그래프가 계산한다.** 물리 그래프의 교통 간선은 GNN 메시지 전달과 접근성 요약에 사용한다.

### 3. 노드 특징

| 그룹 | 권장 특징 |
|---|---|
| 수요 | `expected_concurrent_demand[t,s]`, 65·75·85세 이상 인구, 취약성, 수요 신뢰구간 |
| 기존 공급 | 시설 유형별 개수, `capacity[type,t]`, 잔여용량, 운영시간, 운영상태 |
| 현재 접근성 | 최근접 시설 비용, 10/15/30분 내 유형별 공급, 현재 미수용률, 대안 시설 수 |
| 교통 | 정류장·역·노선 수, 시간대별 배차, 저상버스·엘리베이터·에스컬레이터 정보 |
| 보행환경 | 보행거리, 경사, 계단, 횡단, 단절, 하천·철도·대형도로 장벽, 결측 플래그 |
| 후보지 | 후보 상태, 가능한 필지 수, 토지가, 건폐율·용적률, 최대 면적·용량·사업비 |
| 공간·정책 | 좌표 인코딩, 대상구 여부, 경계 격자, 기존 시설 동시입지, 시설 이용자격 요약 |
| 순차배치 | 남은 예산, 남은 시설 수, 이전 신설 용량, 현재 단계 |

수요는 더 이상 `고령인구 × 고정 이용률`로 정의하지 않는다.

\[
d_{i,t,s}=\text{격자 }i\text{의 시간대 }t\text{ 예상 동시 이용자 수}
\]

고령인구는 수요 예측의 prior와 설명변수다. 수요값은 시나리오 사이에서 변경할 수 있지만, 에이전트가 에피소드 안에서 변경하거나 보상 분모에서 제거할 수 없다.

공급도 하나의 스칼라로 합치지 않는다.

\[
K_{i,r,t}=\sum_{j\in facilities(i,r)}K_{j,r,t}
\]

여기서 \(r\)은 경로당·노인복지관 같은 서비스 유형이다. 서로 대체할 수 없는 시설 용량을 합치면 존재하지 않는 공급이 만들어진다.

최소 권장 노드 벡터는 다음과 같다.

\[
x_{i,t,s}=[
\log(1+P_i),
\log(1+d_{i,t,s}),
\log(1+K_{i,r,t}),
A^{10}_{i,r,t},A^{15}_{i,r,t},A^{30}_{i,r,t},
g^{nearest}_{i,r,t},
R^{bus}_{i,t},R^{rail}_{i,t},
q_i^{parcel},pos_i,m_i
]
\]

`q_i^{parcel}`에는 격자 내부의 최적 필지에 대해 미리 계산한 최대 연면적, 예상 동시수용량, 총사업비, 타당성 상태가 포함된다. 이는 의사결정 시점에 알 수 있는 정보이므로 target leakage가 아니다. 반면 신규 시설을 설치한 뒤의 배정량과 실제 보상은 입력에 넣지 않는다.

### 4. 간선 설계

#### 도보·공간 간선

단순 8방향 격자는 공간 문맥용으로만 사용한다. 경로 비용을 계산하는 보행 간선은 [서울 보행자도로 네트워크](https://data.seoul.go.kr/dataList/OA-21208/S/1/datasetView.do)처럼 실제 node-link 자료로 구성하고, 자치구별 파일을 경계에서 stitch한다.

```text
[distance_m, walk_time_min, slope, stair_count,
 crossing_count, barrier_score, accessibility, missing_flags]
```

- 교통수단이 있는 격자에서도 도보 간선을 제거하지 않는다.
- 하천·철도·차량전용도로를 가로지르는 가상 대각 간선을 만들지 않는다.
- 보행속도는 기본 0.85m/s, 취약 0.70m/s, 낙관 1.12m/s로 평가한다.

#### 버스·철도 간선

노선의 연속 정차 지점을 방향별로 연결한다.

```text
[in_vehicle_time, headway, expected_wait, reliability,
 seat_probability, crowding_level, boarding_barrier, service_active]
```

구간 운행시간이 있으면 사용자가 보유한 값을 우선 사용한다. 결측이면 여러 정상 평일의 `노선 × 방향 × 구간 × 시간대` 중앙값으로 대체하고 결측 플래그를 남긴다. 운행하지 않는 시간대는 비용 0이 아니라 `edge_active=false`로 마스킹한다.

### 5. 환승을 위한 상태 확장 경로 그래프

라우팅 상태는 다음과 같다.

\[
s=(location,status,current\_service,last\_service,transfer\_count)
\]

| 전이 | 상태 변화 | 비용 |
|---|---|---|
| 보행 | `(OFF,last) → (OFF,last)` | 보행시간·경사·장벽 |
| 최초 승차 | `(OFF,NONE) → (ON,route)` | 대기·승하차 |
| 동일 노선 주행 | `(ON,route) → (ON,route)` | 좌석·입석 기대 차내비용 |
| 하차 | `(ON,route) → (OFF,route)` | 하차·수직이동 |
| 환승 승차 | `(OFF,old) → (ON,new)` | 환승보행·대기·고정 패널티 |

하차 후에도 `last_service`를 유지한다. 그래야 한 격자를 걸어 다른 정류장에서 승차하는 방식으로 환승을 숨길 수 없다. 같은 노선에 다시 타더라도 새로운 대기와 승하차 비용은 부과한다.

상태 그래프는 GNN 노드를 복제하는 것이 아니라 최단경로와 수요 배분에서만 사용하는 희소 그래프다. loop 없는 단순경로를 사용하고 최대 환승은 2회로 제한한다. 1회 hard cap은 경계 밖의 합리적 경로를 누락할 수 있으므로 사용하지 않는다.

### 6. 고령자 일반화 이동비용

기준 단위는 `좌석·비혼잡 차내시간 1분 = 1 equivalent minute`이다.

\[
g(p)=
1.5T_{walk}
+1.75T_{wait}
+2.0T_{transferwalk}
+\sum_eT^{ride}_e
[p^{seat}_em^{seat}_e+(1-p^{seat}_e)m^{stand}_e]
+5N_{transfer}
+B(p)
\]

| 변수 | 기본값 | 민감도 |
|---|---:|---:|
| 지속 보행속도 | 0.85m/s | 0.70 / 0.85 / 1.12 |
| 일반 보행 | 1.5 | 1.5~2.0 |
| 대기 | 1.75 | 1.75~2.25 |
| 환승보행 | 2.0 | 1.91~2.11 |
| 좌석·비혼잡 | 1.0 | 비용 하한 |
| 좌석·혼잡 | 1.3 | 1.1~1.5 |
| 입석 | 1.6 | 1.4~2.4 |
| 좌석확률 | 0.5 | 0.2 / 0.5 / 0.8 |
| 고정 환승 | 5분 | 0 / 5 / 11.2분 |

[고령자 보행 연구](https://idea.seoul.go.kr/upload/suggest/20251127/64D4851EB32848C39BBDFE5FC3006D36.pdf)는 평균 약 1.12m/s, 하위 15백분위 약 0.85m/s를 보고한다. [고령자 이동행태 SP 연구](https://pure.uos.ac.kr/en/publications/exploring-the-travel-behavioral-differences-for-the-elderly-mobil/)에서는 환승시간을 차내시간보다 약 1.91~2.11배 무겁게 평가했다.

대기는 최초 승차와 환승 승차에서만 부과한다. 규칙적 배차는 `headway/2`, 시각표 기반 경로는 다음 출발시각까지의 기대 대기를 사용한다. 매 주행 구간마다 대기시간을 더해서는 안 된다.

좌석 편안함은 좌석시간을 음수 보상으로 만드는 대신 보행·대기·입석보다 낮은 양의 가중치로 표현한다. 이 방식이면 조금 더 오래 걸리는 좌석 이동은 선택될 수 있지만, 오래 순환할수록 비용은 항상 증가한다.

### 7. 접근 기준과 사각지대

[생활SOC 국가최저기준](https://www.codil.or.kr/filebank/original/RK/OTKCRK230572/OTKCRK230572.pdf)은 마을 단위 경로당 접근 목표를 도보 5~10분으로 제시한다. [2022 서울시 노인실태조사 재분석](https://council.jungnang.go.kr/kr/bbs/download.do?bbs_id=active&uid=ABC300ABF0C990005BE090C1191909EF)에서 서울 경로당의 실제 평균 편도 이동시간은 약 10.5분이다.

시계시간과 일반화비용을 분리한다.

- 선호 기준: \(g_{pref}=15\), 즉 10분 직접도보의 일반화비용
- 절대 상한: 실제시간 30분 이하이면서 \(g\le45\)
- 강건성 평가: 실제시간 상한 20/30/40분
- 결과 보고: 10분·15분·30분 접근권을 모두 표시

격자 \(i\)의 사각지대 비율은 다음과 같다.

\[
z_i=
\frac{u_i+\sum_jx_{ij}\mathbf{1}[g_{ij}>15]}{\max(d_i,\epsilon)}
\]

즉 미수용 수요뿐 아니라 시설에는 배정되었지만 선호 접근기준을 넘은 수요도 사각지대에 포함한다. 수요가 0인 격자는 $z_i=0$으로 반환한다.

### 8. 필지·예산·용량 특징

후보지는 격자가 아니라 필지·건물 단위로 검토한 뒤 격자로 집계한다.

| 상태 | 의미 | 정책 처리 |
|---|---|---|
| `FEASIBLE` | 공개자료상 예산·법규·면적 요건 충족 | 선택 가능 |
| `HARD_EXCLUDE` | 도로·하천·철도·예산·최소요건 등 불충족 | 선택 불가 |
| `REVIEW_REQUIRED` | 지구단위계획·경관·보전·공원 특례 등 심의 필요 | 조건부 대안으로만 표시 |
| `UNKNOWN` | 필수 데이터 결측 | 실사업 추천에서 선택 불가 |

같은 격자에 기존 시설이 있어도 다른 필지나 증축안이 있으면 후보가 될 수 있다. 기존 시설 존재는 후보 제외 조건이 아니라 `co_located` 특징이다.

총사업비와 최대 연면적은 다음과 같이 계산한다.

\[
Cost(p,A)=Land(p)+Demolition(p)+c_{build}(A)A+Design+Supervision+Utility+Permit+Contingency
\]

\[
A_p^*=\max_A A
\]

subject to:

\[
Cost(p,A)\le B,\quad
A\le FAR_pA_{site},\quad
A_{footprint}\le BCR_pA_{site}
\]

신규 동시수용량은 다음과 같다.

\[
A_{program}=\eta A_p^*-A_{fixed},\qquad
K_{new,p}=\left\lfloor\frac{A_{program}}{a_{user,type}}\right\rfloor
\]

`a_user,type`은 법정 밀도가 아니다. 비교 가능한 운영 시설의 `순사용면적/실제 동시수용량` 분포에서 이상치를 제거하고 보수적인 75백분위로 추정한다. [노인복지법 시행규칙 별표 7](https://www.law.go.kr/LSW/flDownload.do?bylClsCd=110201&flSeq=43368529&gubun=)은 서울 경로당에 이용정원 20명 이상과 거실·휴게실 20㎡ 이상을 요구하지만, 두 최소값을 1㎡당 1명으로 환산할 근거는 없다.

[서울시 2024 공공건축물 공사비 가이드](https://opengov.seoul.go.kr/og/com/download.php?dname=2024%EB%85%84+%EA%B3%B5%EA%B3%B5%EA%B1%B4%EC%B6%95%EB%AC%BC+%EA%B1%B4%EB%A6%BD+%EA%B3%B5%EC%82%AC%EB%B9%84+%EC%B1%85%EC%A0%95+%EA%B0%80%EC%9D%B4%EB%93%9C%EB%9D%BC%EC%9D%B8.pdf&dtype=basic&nid=32033304&rid=F0000107846063&uri=%2Ffiles%2Fdcdata%2F100001%2F20241023%2FF0000107846063.pdf)의 경로당 신축단가는 200㎡ 미만 385.2만원/㎡, 200~400㎡ 374.2만원/㎡, 400㎡ 초과 368.5만원/㎡다. 토지·철거·설계·감리 등은 별도이며 발주시점 공사비지수로 보정한다.

### 9. 마스킹

```text
node_valid_mask[N]
target_demand_mask[T,S,N]
candidate_mask[N]
facility_eligibility_mask[T,N,J]
edge_active_mask[relation,T,E]
selected_mask[step,N]
time_mask[T]
```

후보지 마스크는 다음과 같다.

```text
candidate_mask =
    node_valid
  & is_target_jurisdiction
  & (candidate_status == FEASIBLE)
  & budget_feasible
  & ~already_selected
```

- 인구가 0인 격자도 주변 수요를 서비스할 수 있으므로 제외하지 않는다.
- 정류장이 없는 격자도 도보 접근이 가능하므로 제외하지 않는다.
- 기존 시설이 있는 격자를 자동 제외하지 않는다.
- 수요가 없는 외부 격자도 경로와 메시지 전달을 위해 유지한다.
- 운행 중단 간선은 비용 0이 아니라 비활성 처리한다.

### 10. 형평성 우선 수요 배분

수요 \(d_{i,t}\), 시설 용량 \(K_{j,r,t}\), 배정량 \(x_{i,j,t}\), 미수용량 \(u_{i,t}\)에 대해 다음 hard constraint를 적용한다.

\[
\sum_jx_{i,j,t}+u_{i,t}=d_{i,t}
\]

\[
\sum_ix_{i,j,t}\le K_{j,r,t}
\]

\[
x_{i,j,t}=0\quad\text{if}\quad eligible_{i,j,t}=0\ \lor\ T_{i,j,t}>30\ \lor\ g_{i,j,t}>45
\]

배분 목적은 임의 가중합이 아니라 다음 사전식 순서를 사용한다.

\[
\operatorname{lexmin}
\left(
U,\ CVaR_{0.9}(g),\ Z,\ \bar g,\ Cost
\right)
\]

- \(U=\sum_i u_i\): 총 미수용 수요
- \(CVaR_{0.9}\): 접근부담 상위 10%의 평균
- \(Z\): 선호 기준을 넘는 사각지대 수요
- \(\bar g\): 배정된 이용자의 평균 일반화비용
- `Cost`: 정책 효과가 동일할 때의 총사업비

가장 가까운 시설부터 단순히 채우지 않는다. 대안이 많은 이용자를 두 번째 시설로 보내고, 가까운 대안이 하나뿐인 이용자에게 희소한 용량을 남기는 것이 형평성 목적에 부합할 수 있다.

### 11. 정책 출력과 학습 전략

P0에서는 별도의 시설규모 head를 사용하지 않는다.

\[
a\in\{i\mid candidate\_mask_i=1\}
\]

\[
score_i=MLP([h_i\Vert h_G\Vert q_i^{parcel}])
\]

신규 시설이 1개일 때는 모든 `FEASIBLE` 후보를 정확 배분 솔버로 평가할 수 있다. 이를 P0의 ground truth로 사용한다.

1. 모든 후보의 예산·면적·용량 계산
2. 모든 후보의 수요 배분과 사전식 목적 계산
3. 정확 최적 후보와 전체 순위 생성
4. GNN ranking 모델 사전학습
5. 추론 시 GNN 상위 `k`개를 정확 솔버로 재평가

이 구성은 강화학습의 불안정성과 보상 해킹을 줄이면서도 GNN이 대규모 시나리오의 후보를 빠르게 줄이는 역할을 하게 한다.

여러 시설로 확장할 때는 남은 예산·추가 공급·미수용 수요를 상태에 반영하고 매 단계 전체 배분을 다시 실행한다. 총예산을 공유한다면 행동을 `(격자, cost-capacity Pareto 사업안)`으로 확장한다. 순수 greedy 대신 beam search나 rollout을 우선하고, 충분한 시나리오가 생긴 뒤 PPO·actor-critic과 비교한다.

### 12. 보상과 Reward Hacking 불변식

설치 전과 후의 목적 벡터를 같은 시나리오에서 비교한다.

\[
R(a)=J_{baseline}-J_{after(a)}
\]

`R`은 임의 가중합 한 개보다 `미수용·CVaR90·사각지대·평균비용`의 다중 head와 사전식 action comparator로 구현한다. 하위 목적이 상위 목적을 뒤집지 못하게 한다.

| 공격적 최적화 가능성 | 환경 수준 방어 |
|---|---|
| 가까운 곳도 교통수단 강제 이용 | 순수도보 경로를 항상 후보에 포함, 탑승 자체 보상 금지 |
| 앉아서 오래 순환 | 좌석비용도 1.0 이상의 양수, loop·dominance 제거 |
| 하차 후 걸어서 환승 숨김 | `last_service`를 하차 후에도 유지 |
| 배차가 긴 노선 과대평가 | 승차 시 실제 대기 또는 `headway/2` 부과 |
| 운행하지 않는 노선 사용 | `edge_active=false` 마스킹 |
| 먼 시설로 보내 이용률 균등화 | 이용률 분산을 보상에서 제외 |
| 수용량 초과 | 배분 솔버 hard constraint |
| 미도달 수요 삭제 | 모든 미도달 수요를 `u_i`에 보존 |
| 수요를 줄여 개선률 과장 | 설치 전 전체 수요로 분모 고정, 수요는 외생 입력 |
| 다른 시설유형의 가상 공급 | `K[node,type,t]`로 분리 |
| 불법·결측 필지 선택 | `FEASIBLE`만 action 허용 |
| 유리한 교통 시나리오 선택 | 설치 전후 동일 시간대·난수 시드 사용 |
| 행정경계로 불리한 경로 삭제 | 수도권 전체 경로망 유지 |

### 13. 구현 가능한 텐서 스키마

```python
# 물리 격자
x_static:              FloatTensor[N, F_static]
x_time:                FloatTensor[S, T, N, F_dynamic]
pos:                   FloatTensor[N, 2]

population_raw:        FloatTensor[N]
demand_raw:            FloatTensor[S, T, N]
capacity_raw:          FloatTensor[T, N, R]
facility_count:        LongTensor[N, R]

candidate_status:      LongTensor[N]       # feasible/exclude/review/unknown
candidate_cost:        FloatTensor[N]
candidate_gfa:         FloatTensor[N]
candidate_capacity:    FloatTensor[N, R]

node_valid_mask:       BoolTensor[N]
target_demand_mask:    BoolTensor[S, T, N]
candidate_mask:        BoolTensor[N]
selected_mask:         BoolTensor[K, N]
time_mask:             BoolTensor[T]

# relation r ∈ {spatial, walk, bus, rail}
edge_index[r]:         LongTensor[2, E_r]
edge_attr[r]:          FloatTensor[T, E_r, F_edge_r]
edge_active[r]:        BoolTensor[T, E_r]
route_id[r]:           LongTensor[E_r]
direction_id[r]:       LongTensor[E_r]
mode_id[r]:            LongTensor[E_r]

# 상태 확장 경로 그래프
state_location_id:     LongTensor[Q]
state_status:          LongTensor[Q]
state_current_service: LongTensor[Q]
state_last_service:    LongTensor[Q]

route_edge_index:      LongTensor[2, E_state]
route_edge_cost:       FloatTensor[T, E_state]
route_edge_type:       LongTensor[E_state]
route_edge_active:     BoolTensor[T, E_state]

# 정책·평가 출력
location_logits:       FloatTensor[B, N]
objective_heads:       FloatTensor[B, N, 4]  # unmet, CVaR, blindspot, mean cost
```

정책 출력 직전에 반드시 마스킹한다.

```python
location_logits[~candidate_mask] = -inf
```

학습 입력에는 현재 상태의 접근성만 넣는다. 신규 시설을 설치한 뒤의 배분량·보상·잔여용량을 입력에 넣으면 후보 위치 정답을 노출하는 target leakage가 된다. 정규화 통계는 학습 지역에서만 계산하고, 배분·용량 제약에는 정규화되지 않은 원래 단위를 사용한다.

### 14. 데이터 품질과 검증 계약

[서울시 경로당 현황](https://data.seoul.go.kr/dataList/OA-15052/S/1/datasetView.do)의 시 전체 파일은 시설명과 주소 확인에는 유용하지만 행별 좌표·동시수용량·순사용면적·운영상태를 제공하지 않는다. 현재 확인된 운영 동시수용량은 0건이므로 자치구 설치·변경 신고대장과 현장 표본을 `source_record_id`로 결합해야 한다. 회신 전에는 `STRICT_UNKNOWN`과 `LEGAL_NOMINAL`을 분리하고, 고정 8명·회원수·일평균 방문자는 동시수용량으로 사용하지 않는다.

후보지는 [연속지적도](https://www.data.go.kr/data/15123899/openapi.do), [토지이용계획정보](https://www.data.go.kr/data/15123973/openapi.do), [서울 개별공시지가](https://data.seoul.go.kr/dataList/OA-1180/F/1/datasetView.do), 실제 토지거래 자료를 결합한다. 공개 공간자료는 1차 검토용이므로 최종 추천에는 필지별 인허가 확인 상태를 함께 표시한다.

완료 기준은 다음과 같다.

- 모든 수요가 배정 또는 미수용으로 보존된다.
- 모든 시설의 유형별 동시수용량을 초과하지 않는다.
- 불법 후보와 운행 중단 간선이 단 한 번도 선택되지 않는다.
- 광운대역→석계역처럼 경계 밖 합리적 경로가 재현된다.
- 짧은 직접도보가 불필요한 대중교통 경로보다 우선된다.
- 좌석확률·보행속도·수요·건축단가 시나리오가 달라도 상위 후보의 안정성을 보고한다.
- exact enumeration 대비 GNN top-k recall, regret, 추론시간을 함께 측정한다.
