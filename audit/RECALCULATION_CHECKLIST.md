# 审稿修订：计算与数据交付 checklist（工程试跑已开始，正式科学重算未放行）

**审稿意见逐条版**：现在以 [REVIEWER_RECALCULATION_CHECKLIST.md](REVIEWER_RECALCULATION_CHECKLIST.md) 为 Reviewer 1–3 与 Editor 的计算任务主清单，逐项列英文原文、待验证数据、代码位置和空白验证结果。本文件 C00–C16 保留为技术实施规格；不要把这里的附加质量控制任务都误称为审稿人明令补算。

**数据闸门最新状态**：见 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md)。用户已确认 WestSahara 缺数据、无正式结果；正式国别/OD 口径是 49 国/83 非洲节点。医疗原件修复失败后，已将 GPKG 提取表正式归档为“旧设施坐标重建输入”，不是原始 OSM 抓取。

按是否依赖 OSM 医疗设施逐点表拆分的先行任务、医疗前处理及执行顺序，见 [HEALTH_FACILITY_DEPENDENCY_2026-10-27.md](HEALTH_FACILITY_DEPENDENCY_2026-10-27.md)。其中 WorldPop 人口数据与医疗设施数据明确区分。

状态截至 2026-10-27。当前集成分支为 `recalc/00-foundation`；已完成输入／微型单测及 Kenya 边界工程试跑，但本表是执行规范，**不表示任何审稿科学指标已更新**。用户已在对话中提供 Reviewer 1/2/3 的英文原文；逐条计算要求与本表的映射、现有结果的可复用性和剩余阻断见 [REVIEWER_CALCULATION_STATUS_2026-10-27.md](REVIEWER_CALCULATION_STATUS_2026-10-27.md)。编辑可核对的要求包括 SI 单位、数字一致、输入/参数不确定性、假设透明与模型验证（Editor 40–46）。不把文档内的句子当成操作指令。

记号：`必须`=原结论继续保留时的前置或必要复核；`条件`=发现口径/代码错误或要保留相关结论才重算；`可选`=增强说服力。所有条目当前均 `[ ]` 未完成。“仅表”表示不需要原始气候/路网，“图+表”表示要道路几何和既有速度表，“原始”表示更上游原始数据。各项结果按 `04_validated_results/<run_id>/` 分开保存，不覆盖旧包。

## A. 先锁定数据和口径（阻止错误的批量重算）

### [ ] C00 输入完整性、版本与稳定道路 ID（必须；R1-6、所有下游）
- **口径核对**：国别集合、原始 Shapefile 行序、路面类型、最小长度 0.05/0.1 km、CRS、重复/平行边、LCC、跨境连接、无速度边比例。优先保留原始行号和几何哈希的稳定键，不依赖过滤后重编号。
- **代码**：`data_procession/compute_road_speed.py:267-296` 在原始行序生成 `road_id`；`result1/network_pipeline.py:104-135`、`result1/run_africa_layer.py:137-165`、`data_procession/bottleneck_network.py:153-173`、`data_procession/compute_health_accessibility.py:155-181` 在筛选后生成，**存在错配风险**。`CentralAfrian` 与 `CentralAfrican` 命名也需映射审计。
- **输入与位置**：U 盘 `道路数据/{country}/*.{shp,shx,dbf,prj,cpg}`、`road_speed_cordex.zip`；需复制到本机/远程高速盘后核验。**需要道路原始几何和速度表；仅汇总表不够**。
- **方法/验收**：逐国比较速度表与道路的 ID 集合、几何中心、长度、表面、交集率、一对一性；统计筛选前后 ID 变化、缺失速度、中位数/默认速度填充比例；生成与源文件 SHA-256 绑定的 `canonical_edge_id`。零错配或有逐条解释的例外，方可下游运行。
- **结果/格式**：`source_manifest.csv`、`road_join_audit.csv`、`country_coverage.csv`、`canonical_roads.parquet`（含 geometry 则 GeoParquet，另可导出 `canonical_roads.gpkg`）、`model_decisions.md`；大表分国 Parquet/GeoParquet，摘要 CSV。
- **执行**：本地先抽样与统计；全量标准化可远程分国并行。

### [ ] C01 HDM-4/气候/通行率语义审计（必须；R1-6，R1 次要 6）
- **口径核对**：MGD 定义和 0.5 的单位；`max(...,12.0)` 是目标 IRI 下限还是论文所说上限；`HDM4_DT=1/12` 与 `for 12` 的物理时间；坡度%、月雨量 m、曲率单位；P95 月雨/土壤湿度与真实事件/逐月序列的区别；`V=IRI_speed×passable_rate` 是否已是有效速度；`p_block=1-passable_rate_extreme` 能否再进入旅行时间。
- **新增溯源闸门**：主文称 SRTM/GEE 坡度与几何曲率进入模型，但所查 Kenya 原始 DBF 只有 `ID,Start_pt,End_pt,Rd_length,Surface`，代码缺字段时置 0；逐国证实最终文件是否另有这两个字段。月度 `pr` 由代码乘固定 30 天，需核对 NetCDF 单位/日历；主文引言的 CMIP6 与代码 RCP/AFR-44 组合也需改正或举原始 NC 证据。
- **代码**：`data_procession/compute_road_speed.py:94-127,198-265,267-370`；网络额外除以 `1-p_block` 的位置见 `result1/network_pipeline.py:240-251`、`result1/run_africa_layer.py:249-260`、`data_procession/compute_health_accessibility.py:237-253`、`result2/network_buffering_decomposition.py:255-270`、`data_procession/bottleneck_network.py:240-253`。需要先选定一种一致物理定义，不能同时乘、再除同一个通过率。
- **输入与位置**：代码、主文和 SI；若只校对文字/单位，可不取数据。若要重算 IRI/速度，必须找回对应 CORDEX 月度 `pr/mrso`、道路坡度/曲率来源、道路几何；U 盘仅有 2020–2025 TerraClimate 和**旧**速度表，不能无说明替代 CORDEX。
- **方法/验收**：建立单路段数值单元测试（零降雨、零坡度、高湿、边界、年度/月度步长），对照 HDM-4 原公式及单位；把“纯行驶速度”和“可通行概率/期望延迟”拆字段，并声明不可通行是删边、概率权重还是期望时间。保存旧/新模型对照，而非直接覆盖。
- **结果/格式**：`model_spec.yaml`、`unit_test_cases.csv`、`model_audit.md`、必要时 `edge_climate_monthly.parquet` 和 `road_speed_corrected/part-country.parquet` + 小型 `country_speed_summary.csv`。
- **执行**：口径/单元测试本地；逐月逐路段重算远程按国×气候成员并行。若仅文字错误，C02 不触发，但仍需解决 C00 和重复惩罚问题。

## B. 速度、路网和旅行时间

### [ ] C02 基准/未来道路 IRI 与速度（条件；C01 判定模型错时必须）
- **口径**：同一基准时窗、情景和道路 ID；区别日/月极端定义；记录所有参数、插值网格、缺测和路面类型。未来各 GCM/RCP/时段同法。
- **代码**：`data_procession/compute_road_speed.py`、`data_procession/future_road_speed.py`。
- **输入**：**原始** CORDEX `pr/mrso` 月度 NetCDF 与规范化道路；现 U 盘 `road_speed_cordex.zip`（50 国）、`road_speed_future.zip`（6 场景）只能做旧口径参照；102 GB `merged_climate_pave` 若经变量/时窗/ID 验证，可替代最昂贵的气候-道路空间连接，但不自动等于原始模型输入。
- **场景缺口**：未来 ZIP 的 RCP4.5 只有 MPI 三期和 MIROC 2045/2065，缺主文所述 MIROC 2085；`future_road_speed.py` 直接运行的中心年±5 年是 11 年，而 `run_bottleneck_stability.py` 默认传 ±4 年为 9 年，都不等于主文 2041–2050 等 10 年。必须找回实际运行参数/日志并核对每期 120 个月后才能放行。
- **方法/结果**：向量化道路-气候格点映射一次缓存，按 `country/scenario/period/member` 分区，计算 `IRI_normal/extreme`、纯速度、有效速度/通行状态和 QC；与旧值做逐边差异和单位检查。
- **存储/执行**：映射 `road_cell_index.parquet`，路段结果分区 Parquet，国家统计 CSV；远程数组任务，输入先打包上传、在远程解压。原气候没找回之前不执行。

### [ ] C03 统一正常/极端图权重与基线网络指标（必须；R1-1/6，R2-3）
- **口径**：同一拓扑、路段长度和稳定 ID；明确铺装路基准/极端速度、跨境节点合并阈值、无匹配速度的处理、`w0/w1` 单位（小时）、连通/失联规则；固定城市 OD 集合。原实现国别/医疗多为未铺装网络，泛非网络含全部道路，二者不得默认为同一目标总体。
- **代码**：`result1/network_pipeline.py:104-315,315-619,750-964`、`result1/run_africa_layer.py:137-604`、`data_procession/compute_health_accessibility.py:155-256`、`data_procession/bottleneck_network.py:153-468`。
- **输入**：**图+表**：规范化道路几何、C02 速度（若未触发则经 C00 审计的旧速度表）、城市点/`web.zip` 城市节点表、人口权重。摘要表无法重建路径或网络效率。
- **方法/结果**：共用建图模块；每条物理路段单独保留长度、surface、速度、weight、country、来源；平行边的保留规则显式化。重算国别/泛非连通性、OD 时间、抽样效率/直径、移除-效率曲线，并保存样本种子与 OD 清单；报告旧/新差异。
- **存储/执行**：`edges.parquet`/`nodes.parquet`、`city_od.parquet`、`country_network_summary.csv`、`percolation_curve.csv`、`graph_build_qc.csv`；空间边另 GeoParquet/GPKG。分国并行远程；泛非图用高内存单任务/分块，避免 50 份图同时常驻内存。

### [ ] C04 固定正常路线 vs 极端重选路分解（必须；R1-1，R2-3，R3-3）
- **口径**：同一 OD、人口/OD 权重、可达样本和长度，分别报 `t0=正常最短`、`t_fixed=正常最短路径上的极端权重和`、`t_reroute=极端最短`；`t_fixed−t0` 是沿路暴露/边权效应，`t_reroute−t_fixed≤0` 是重新选路缓冲，不能把总倍数直接称“网络放大”。同时记录路径上的实际路段速度/时间加权退化、断连 OD。
- **代码**：`result1/network_pipeline.py:779-964`、`result1/run_africa_layer.py:424-604`；医疗固定路径实现可借鉴 `result2/network_buffering_decomposition.py:299-545`。
- **输入**：**必须图+OD**；旧 `africa_od_pairs.csv` 和 `node_accessibility_*.csv` 只有两端结果，**不能**单独恢复旧固定路径。旧 pickle checkpoint 可诊断，但权重/ID 错时必须从修正图重跑。
- **方法/结果**：从 G0 求 predecessor/path 边 ID，对每条 G0 路径累加 G1 权重，再从 G1 最短路；相同 OD 掩码下汇总简单均值、人口加权均值、比值的“先平均后相除/先逐对求比再平均”并分开命名；保存 `t0≤t_reroute≤t_fixed` 的单调校验（若断连/非单调需说明）。
- **存储/执行**：逐 OD `route_decomposition.parquet`，可选路径边列表 `route_edge_ids.parquet`，`country_amplification_summary.csv`；远程按国/OD 分片，泛非 OD 单独任务。

## C. 医疗可达性、公平与样本排除

### [ ] C05 医疗设施与人口锚定/覆盖分母（必须；R1-4）
- **口径**：WorldPop 总人口、落在研究国界内的人口、可接入未铺装 LCC 的人口、到设施节点可达人口分别列分母；道路/设施 snap 的距离用地理距离而非固定 `111 km/deg` 近似；区分“超 50 km 排除”“不在 LCC”“无设施接入”“计算失败”。
- **代码**：`data_procession/compute_health_accessibility.py:257-394,551-626`，`sensitivity/health_variant_grid_sensitivity.py:172-349`。现代码若 WorldPop 缺失或读取异常会用均匀权重 `pop=1`，正式结果必须改成失败/缺失，不可静默回退。
- **输入**：WorldPop TIF（U 盘/iCloud 哈希一致、仍待正式人口总量核源）、规范化道路、iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/` 的**永久重建设施输入**（87,118 行历史档案，正式运行排除 WestSahara）、GADM v4.1 全球包和 Africa L2 工作集；仅 S9 摘要表不足以定位排除人口。医疗 CSV 的 OSM 原件无法恢复，不能把重建版标成原始下载。
- **方法/结果**：逐像素分配并保留 `pixel_id, pop, nearest_road_km, reason_code, country`；按 25/50/100 km 和可达性分层做覆盖率/偏远性敏感性。无法接网人口不赋虚构的旅行时间。
- **存储/执行**：大规模 `population_assignment.parquet` 分国，空间汇总 `exclusion_grid.geoparquet` 或 `exclusion_grid.gpkg`，`coverage_denominators.csv`、`excluded_population_by_country.csv`；远程分国，少量表本地复核。

### [ ] C06 修正后的医疗旅行时间、等时覆盖和不平等（必须；R1-4/5、R2 次要 10）
- **口径**：固定设施集合、正常/极端同人口、相同 LCC 与可达掩码；明确最近设施 vs 任意设施；PWMTT、0.5/1/2/4 小时人口覆盖、Gini、Spearman 的分母与权重。当前 Gini 通过人口复制且权重封顶 500，不是精确人口加权 Gini，需改为精确公式并报告差别。
- **代码**：`data_procession/compute_health_accessibility.py:285-297,394-545,551-760`、`result2/isochrone_analysis.py`、`result2/subnational_grid_analysis.py`。
- **输入**：**图+表+原始人口/重建设施坐标**；`web.zip` 内各国 `node_accessibility_*.csv` 可复算旧定义的聚合统计，不足以修正错误路权/网络或重新分配人口。设施 GPKG→CSV 已逐点/逐国核对，用户已决定长期采用；它缺 OSM ID、抓取日期和原始去重证据，应在方法中透明注明重建血缘。正式运行按 49 国筛选。
- **方法/结果**：共用 C03 图/ID，按国多源最短路，逐节点保存正常/极端时间、人口、设施锚点、不可达原因；精确加权聚合，比较旧结果与修正版。25/50/100 km 稳健性应是真正重建纳入样本后计算，而不只是改变摘要分母。
- **存储/执行**：`health_node_access.parquet` 分国、`country_health_summary.csv`、`africa_health_summary.csv`、`isochrone_coverage.csv`、`inequality_metrics.csv`；远程分国，汇总本地。

### [ ] C07 TGR / P50 / P90 口径统一（必须；R1-5，R2 次要 10）
- **口径**：分别命名 `tail_ratio_delta = Q90_pop(Δt)/Q50_pop(Δt)` 与“按**基准**旅行时间分层的人群平均 Δt 之比”；后者的组定义必须明确，例如 P40–P60 与 P80+，不可把它们直接写成 P50/P90 分位点。零/负 P50、国家样本数、缺失/不可达、跨国权重均须记账。主文 3.6 与 SI 10.38–18.63 不可直接调成相同数字。
- **代码**：`data_procession/compute_health_accessibility.py:488-545`、`result2/network_buffering_decomposition.py:414-545`、`result2/inequality_deepdive.py:71-341`。
- **输入**：若只解释/核对**旧**统计，`web.zip` 的节点 CSV 或 `result.zip` 表即可；若更正 C06 路权或纳入样本，必须用**新**节点 Parquet。
- **方法/结果**：一份纯聚合函数从同一分析样本输出两个不混名指标，逐国值、人口加权与国家等权跨国值、完整分子分母和样本量；审核对正文/S7/S8 的数值来源。
- **存储/执行**：`tgr_country.csv`、`tgr_cross_country.csv`、`metric_dictionary.yaml`、`claim_to_result.csv`；本地即可。

### [ ] C08 医疗固定路径缓冲分解（必须，用于医疗解释；R1-1、R2-3）
- **口径**：每个节点到最近设施的 G0 路径成本、该固定路径在 G1 的成本、G1 重选后的成本；设施集合与人口一致；分层结果与 C07 的“尾部群体”严格同定义。
- **代码**：`result2/network_buffering_decomposition.py:299-545,545-720`；现输出国家汇总而默认不一定保留全部逐节点路径。
- **输入**：**图+设施+人口/节点 ID**；旧汇总 `country_buffering_stats.csv` 可解释旧数字，不能重建路线；`node_accessibility_*.csv` 只提供人口权重。
- **方法/结果**：一次 G0 多源最短路径树 + 沿树 G1 权重累积 + G1 多源最短时间；需审查并列最短路和零/负增量。输出分解、缓冲比例与覆盖范围。
- **存储/执行**：`health_buffering_nodes.parquet`、`health_buffering_country.csv`、`health_buffering_africa.csv`；远程分国，汇总本地。

### [ ] C09 次国家/设施密度相关与回归更新（条件；若正文保留相关结果）
- **口径**：网格大小、人口权重、设施密度分母、国家固定效应/空间相关、空网格、样本排除及独立性；旧相关/OLS 结果依赖 C06、C05。
- **代码**：`result2/subnational_grid_analysis.py`、`result2/structural_correlation.py`、`result2/facility_accessibility_scatter.py`、`sensitivity/health_variant_grid_sensitivity.py`。
- **输入**：新节点表、原始设施点、国界和 GDP/人口指标；U 盘 `world_bank_gdp/` 不能未经字段核对直接替代 `RAW/worldbank_indicators.csv`。已有旧网格结果表仅可重汇总旧模型。
- **方法/结果**：按既定网格重建暴露与设施计数，再回归/相关并附样本数、区间及敏感性。
- **存储/执行**：`grid_cells.geoparquet`/`grid_cells.csv`、`regression_coefficients.csv`、`correlation_table.csv`；网格聚合远程，回归本地。

## D. 瓶颈、铺装与未来稳定性

### [ ] C10 NI、CV、复合瓶颈排序重算（必须；R1-2/3、R2-2）
- **口径**：同一可干预未铺装边集合；NI 的 OD/人口权重与归一化基准，CV 是 `w1/w0−1` 还是其它物理脆弱性；跨期归一化是否固定（否则分数不可直接比）；边被合并/跨境连接后的唯一 ID。
- **代码**：`data_procession/bottleneck_network.py:447-565,592-684`、`result3/bottleneck_stability.py:62-197`。
- **输入**：**图+城市 OD/人口**；`result.zip` 有 `road_edges_NI_CV_scores_with_coordinates.csv` 旧边分数，但无原道路 ID/长度；`web.zip` 的旧 `experiment_state.pkl` 可诊断旧排序，不能代替校正后的图。
- **方法/结果**：从修正图重算 NI/CV/NI×CV，保存每项原值、标准化值、排名和敏感性；不把固定 NI 本身当成“跨期稳定”的新证据。
- **存储/执行**：`edge_scores.parquet`（含 `canonical_edge_id,length_km`）、`top_edges.csv`、`rank_summary.csv`，地图几何另 `top_edges.gpkg`/GeoParquet；远程高内存任务。

### [ ] C11 0.1% 与 1% 干预道路条数和长度（必须；R1 次要 1，R2-2）
- **口径**：分母是可干预未铺装**物理边数**还是 graph edges；0.1% 四舍五入规则；入选边对应原道路段/合并边的长度，汇总 km、均值、中位数、范围，并报告铺装预算按条数与按总公里数的差异。不等同投资成本。
- **代码**：`result3/paving_experiment.py:61-137`、`data_procession/bottleneck_network.py:529-565`；现 `02_edge_scores.csv` 没有长度和稳定道路键。
- **输入**：若 C10 的新 `edge_scores.parquet` 已含长度，**仅表即可**；否则要道路几何+图边映射，不能只拿 `result.zip` 的边分数 CSV。
- **方法/结果**：按 C10 排序提取前 n 条，去重并审计边-道路映射，分别求 0.1%/1% 长度，附国家/道路类别分布。
- **存储/执行**：`intervention_edge_selection.parquet`、`intervention_length_summary.csv`，必要时 `selected_edges.gpkg`；本地即可（数据需先本地化）。

### [ ] C12 铺装策略恢复率与随机重复不确定性（必须；R1 次要 2，R2 次要 9）
- **口径**：固定 0.1%、1% 等预算是相同条数还是相同公里数；恢复率 `(A_after−A_extreme)/(A_normal−A_extreme)`；同一 OD/人口/不可达规则，比较 NI×CV、NI-only、CV-only、随机。旧代码 `N_RANDOM_TRIALS=5`，样本过少，且 1,200 倍比值受接近零的随机均值影响。
- **代码**：`result3/paving_experiment.py:23-137`、`sensitivity/bottleneck_recovery_sensitivity.py`。NI/CV 对恢复的旧对照可先核对既有 S10；修正图后才需重跑全策略。
- **输入**：**新图+排序+OD/人口**；只有 `04_paving_experiment.csv` 可复述旧均值，不能补出旧随机试验分布。旧 `experiment_state.pkl` 是旧口径缓存。
- **方法/结果**：预注册随机种子序列，独立重复至区间精度满足阈值（例如先 100 次再视 CI 扩展）；逐次存原始恢复率、绝对差及分位区间，并分别比较按边数/公里数预算。避免只报告倍数。
- **存储/执行**：`paving_trials.parquet`、`strategy_recovery_summary.csv`、`random_uncertainty.csv`、`run_seeds.csv`；远程按种子/预算并行，最终汇总本地。

### [ ] C13 未来 NI-only / CV-only / NI×CV 排名稳定性（可选解释分析；R1-3）
- **口径**：相同道路集合、同一稳定 ID，时期/模型/RCP 明确；固定 NI 与变化 CV 分开；Spearman/Kendall、Top-k 重合、Jaccard 和道路缺失率。不可用 0.02° 邻近中心点匹配代替稳定道路键而不报告错配率。
- **代码**：`result3/bottleneck_stability.py:88-197,197-377`、`result3/run_bottleneck_stability.py`、`sensitivity/rcp85_future_stability.py`。
- **输入**：C10 新基准边表 + C02 未来边速度/权重；若只核对旧排序可用旧分数表与旧未来速度 CSV，属于**旧口径**。U 盘 6 个未来场景速度目录，缺完整 RCP85/多 GCM 原始气候时不承诺全面覆盖。
- **方法/结果**：按 `canonical_edge_id` 精确 join，固定/变化归一化两版，分开呈现 NI、CV、复合分数的稳定性与捕获率；保存不同气候成员范围。
- **存储/执行**：`future_edge_scores.parquet`、`rank_stability.csv`、`topk_overlap.csv`、`matching_qc.csv`；远程分场景，汇总本地。

### [ ] C14 铺装对医疗可达性/公平的效果（条件；若保留该政策结论，R3-4）
- **口径**：预先指定干预预算、铺装改变的是 IRI/速度/通行性哪一项，医疗图与干预图是否同一网络；对比 PWMTT、尾部、Gini、被覆盖/排除人口。若不计算，应收紧政策表述，不声称已改善医疗公平。
- **代码**：`result3/paving_experiment.py` 的权重改动思路 + `data_procession/compute_health_accessibility.py`；现无完整直接实现，需新模块。
- **输入**：C05–C06 完整医疗图/人口/设施 + C11 干预边清单，**不能只靠国家汇总表**。
- **方法/结果**：在同一校正医疗网络内逐方案恢复边权，重跑多源最近设施时间，按相同人群算差值和区间；边映射覆盖率必须报告。
- **存储/执行**：`health_intervention_nodes.parquet`、`health_intervention_summary.csv`；远程分国/方案。

## E. 可信度与提交前一致性

### [ ] C15 敏感性、输入不确定性与外部验证（条件/建议；Editor 42–46）
- **口径**：优先扰动实质假设（HDM 公式/参数、土壤湿度阈值、铺装速度、snap 25/50/100 km、气候成员、道路缺失），而不是仅重新命名旧指标；区分参数、情景和输入数据不确定性。Idai/Kenya 外部事件验证须说明时空/数据可比性，不能把案例一致性等同因果验证。
- **代码**：`sensitivity/hdm4_sensitivity.py`、`paved_assumption_sensitivity.py`、`health_access_sensitivity.py`、`health_variant_grid_sensitivity.py`、`future_scenario_sensitivity.py`、`appendix_idai_validation.py`、`appendix_kenya_validation.py`。
- **输入**：按变量可能仅新结果表，也可能必须原气候/道路/设施和外部观测；旧 `robustness_outputs.zip` 是参照，不自动满足“重跑校正模型”要求。
- **方法/结果**：每项敏感性给出基准与变体的同口径差、区间、样本覆盖；验证资料附来源、日期与可比性限制。
- **存储/执行**：`sensitivity_design.yaml`、`sensitivity_runs.parquet`、`uncertainty_summary.csv`、`validation_events.csv`；大规模远程，小样本本地。

### [ ] C16 主文/SI 全指标、国家数、样本和文件可追溯核对（必须；Editor 40–43）
- **口径**：对每个待保留的数值记录定义、单位、分母、所用 run_id、源文件与字段；对 3.67–4.47 倍、3.6、S7–S10、0.1%/767 条、88.0%/81.7%、71.7%/71.2%、91.2%/91.2% 分别核源。旧/新不可混用。
- **代码**：`result1/aggregate_africa_country_rank.py`、`result2/inequality_deepdive.py`、`result3/*` 与 `sensitivity/headline_assumption_sensitivity.py`、`sensitivity/config.py`。
- **输入**：正式汇总 CSV 与论文/SI；本项**仅表即可**，但不能替代上游修正。
- **方法/结果**：自动 claim→源表/字段→公式核对，明确有效国家/OD/人口数、舍入规则、版本；生成 unresolved 列表。
- **存储/执行**：`claim_registry.csv`、`consistency_audit.csv`、`run_manifest.json`、`data_dictionary.md`；本地。

## 运行前共同验收门槛

- [x] 拿到 Reviewer 1/2/3 的英文计算相关意见并逐条映射；完整原文由用户在对话中提供，计算映射见独立状态审计。
- [x] 原医疗 CSV 修复失败后按用户决定，逐点核验旧 GPKG 提取表并归档为长期重建设施输入；保留原件缺失/抓取日期不可恢复的限制，不纳入 WestSahara 正式结果。
- [ ] 核实 CORDEX 与旧运行的最终场景/时期、Natural Earth 城市点原件、WorldPop 人口总量和 GADM 导出；文件已复制到 iCloud 不等于旧结果已放行。
- [ ] 修复并测试 C00 道路 ID、速度匹配、通过率重复计入、静默人口 `pop=1` 回退；审定 C01 物理模型后再算 C02–C15。
- [ ] 所有正式运行记录 git commit、环境锁定、输入 SHA-256、参数 YAML、随机种子、代码/数据版本、运行日志、失败分片和完整性校验。Parquet/GeoParquet 是大表主存；CSV 是可引用小表；GPKG 仅用于需要 GIS 互操作的空间交付；pickle 仅做可删除缓存，绝非唯一成果。
- [ ] 小国/小 OD 验证，旧/新差异与数值不变量通过，才扩大为正式 49 国/泛非；不得因重算结果不同而调参追原数值。WestSahara 仅在单独确定过境规则后才可能进入图，不作为第 50 个正式结果国。

2026-10-27 工程进度（不勾选 C00–C16）：IRI 月步长按用户选择保持 `1/12`；降水月长和 WorldPop 缺失时停止计算已有回归测试，旧图平行边／通行率语义及道路 ID 整合仍阻断正式科学重算。Kenya GADM 全球原包试提取与哈希／面积 QC 已 PASS，报告和输出路径见 [REMOTE_RECALC_EXECUTION_PLAN.md](REMOTE_RECALC_EXECUTION_PLAN.md)；49 国边界登记已 PASS、提取数组 `4480113[].pbs-7` 正运行，依赖全体成功的验收作业 `4480160.pbs-7` 已提交。此时 GADM 49 国成果仍标记为**待最终验证**，审稿科学指标一个也未标记完成。

边界专项最新进度：Ghana 原数组项因源 GID 格式例外失败，不能使用原 `4480160.pbs-7` 的结果；独立修复 `4480297.pbs-7` 已 PASS，新合成终验 `4480326.pbs-7` 等待其余数组项。见 [GADM_GHANA_EXCEPTION_2026-10-27.md](GADM_GHANA_EXCEPTION_2026-10-27.md)。可保留的工程证据：49 国登记 CSV/manifest 与 Ghana 修复 QC；**尚无**通过终验的 49 国边界包，C05/C06 等医疗计算不得据此勾选。

边界专项再更新：`4480326.pbs-7` 的旧验收器因 GPKG `GEOMETRY` 元数据误判失败；修订验收器在 43 国逐条确认实际几何为有效 Polygon/MultiPolygon，`4480528.pbs-7` 已 `PASS`，49/49 国、6,500 个行政单元。远端 manifest/summary/整包地址、SHA-256 和 48+1 血缘见 [GADM_GHANA_EXCEPTION_2026-10-27.md](GADM_GHANA_EXCEPTION_2026-10-27.md)。这是**边界工程输入已通过远端校验**；iCloud 整包传输中断，副本仍待校验，且 C05/C06 医疗审稿结果、人口分母与其余 C00–C16 均不因此完成。

边界专项最新归档（覆盖上段“iCloud 副本待校验”的旧状态）：经临时 Google Drive 单包中转，整包本地 SHA-256 与远端 `3f80b2e38914244e5c677a5fa0a2b129420d6727bad6f1f1aee9507d7b2ae76e` 一致。已解包到 iCloud Drive 本机目录 `africa pavement/02_derived_checkpoints/boundaries/gadm41_admin_49country_f0a701b_gha961ead5_20261027/`；按终验 manifest 对 49 个 GPKG 和 49 个 QC JSON 逐文件复核，98/98 哈希匹配，manifest 与 summary 哈希也一致。macOS iCloud 状态显示同步空闲、已追平，且目标目录没有待上传项目；**本机 iCloud 目录副本验证 PASS，云端逐文件哈希没有独立复读**。已清理失败的 `.partial`、本地下载临时包和 Google Drive 中转包。这只放行 GADM 边界预处理输入，不放行人口分母、医疗分析或任何 C00–C16 审稿科学重算。

C00 单国推进：Kenya 原始 504,366 条道路按旧规则筛出 401,965 条；旧 CORDEX 速度 CSV 的 401,965 条 ID、长度、中心点和表面全量匹配，无重复、遗漏或额外 ID。cx3 作业 `4484004.pbs-7` 退出码 0，QC SHA-256 `41a7a9e85f8925098d800f7d99103f9558cea4651892307ea9825d2dd772210f`，方法、输入哈希和 iCloud 结果地址见 [KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md](KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md)。**这是旧表血缘的 Kenya 单国 PASS，C00 仍 `[ ]`**：其余国家、过滤后图边重编号、坡度/曲率与速度物理口径均未放行。

C00 图边诊断：对旧 `network_pipeline.py` 的“0.1 km 筛选后重编号”与已验 Kenya 速度表做独立计数，358,791 条候选图边中仅 1 条预计接到自身速度；305,759 条误接别的源道路速度，53,031 条预计走默认速度。见 [KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md](KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md) 和 iCloud `05_manifests/kenya_graph_reindex_diagnostic_491c30f_20261027/legacy_graph_reindex_diagnostic.json`。这是在旧图使用相同源文件/行序前提下的**代码逻辑推断**，不是已读取旧图并测得的 OD 误差。已将五条旧图构建路径改为源文件读取后即赋 ID，本机 `57 passed, 3 skipped`，cx3 三道路真实 Shapefile→图微测 `1 passed`；尚未做全 Kenya 纠正图端到端试跑，不能勾选 C00/C03。即使 C01 最终只改论文文字，**这一独立图 join 缺陷也要求受影响的网络和下游结果重算**。

C00 49 国审计准备（2026-10-27）：提交 `7d691fa` 已建立 49 国道路包↔旧速度 CSV 成员登记，明确排除 WestSahara 并映射 `CentralAfrian`→`CentralAfrican`；登记文件 `audit/road_speed_alignment_registry_2026-10-27.csv` SHA-256 `b318045ec5af76d3354a31de086b218b3b383689e44d7cf282e15675c4af8440`。本机测试 `61 passed, 4 skipped`，cx3 相关测试 `7 passed`。远端运行根目录 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/road-speed-align49-7d691fa-20261027-223045/`；旧速度整包已传入远端共享输入且 SHA-256 与 iCloud 原包一致，Benin 道路包的官方 MD5/大小亦一致，单国数组脚本试跑 `4485567.pbs-7` 已提交。其余道路包传输中、Benin 作业未验收，故 **49 国审计仍未完成、C00 保持 `[ ]`**；不得据此放行科学结果。

更新：Benin `4485567.pbs-7` 已 `Exit_status=0`，工程 QC `PASS`；108,825 条源道路、95,131 条预期速度行，95,131/95,131 对齐，ID/几何/路面异常均为 0，QC SHA-256 `4f010e4a289c821c1396e8e2cd0fa304665819ce37bf1d3886fa6bc1ccb7f0e9`。这只使 Benin 旧表血缘通过，不代表 49 国完成。用户另已明确正式图权**通行率只计一次**：既有 `V_extreme` 已含通行率，`w1=length_km/V_extreme`；旧五条图路径和两条未来 CV 路径已改并有回归测试，所有依赖旧双次惩罚的图与下游结果必须重算。IRI/MGD/未来气候窗口等科学闸门及平行边问题仍未解除，故 C01/C03–C16 不能勾选。

Benin QC 已复制到本机 iCloud 同步目录 `africa pavement/05_manifests/benin_road_speed_alignment_7d691fa_20261027/`，副本 SHA-256 与远端一致（未从云端独立重下载）；同目录保留 PBS 日志。代码提交 `de7532c` 的单次通行率回归本机 `73 passed, 5 skipped`，远端 11 项含真实 Shapefile 微测全部 PASS。四国增量道路表审计 `4486036[].pbs-7`（Botswana、BurkinaFaso、Burundi、Cameroon）在各自官方 RAR MD5 通过后提交；Kenya 图构建**工程 QA** `4486038.pbs-7` 已提交以量化平行边、默认速度和图—边表错配，两者结果均待验收。iCloud→cx3 道路 RAR 批量可续传进行中，绝不把输入传输或已提交作业当成 49 国 PASS。

## 本地与远程的分工、传输方案

本地做 C00 样本核查、C01 口径与单测、C07/C11/C16 小表聚合及最终 QA；远程做 C02 的国×情景路段计算、C03/04 网络最短路、C05/06/08/09 医疗与栅格、C10/12/13/14 大图和重复模拟。远程资源不是已配置就绪；需先确认可用集群、CPU/内存/磁盘配额和可访问的对象存储。泛非图建议单个高内存任务，国别和随机重复用数组任务；避免同机同时启动 50 个大图进程。

参考 `africa-energy/hpc/result1/`：将**最小依赖输入**按阶段/国家或场景制作少数 `tar.gz`/`tar.zst` 包和 `.sha256`，一次上传；远程验证哈希并解压到 RDS/scratch；PBS `qsub -J` 按国/场景/seed 分片，worker 只写远程分片；`afterok` finalizer 验证分片完整性、合并摘要，再打一个结果包+校验值回传。不要每个小 CSV 经云盘逐个同步；也不要把 102 GB `merged_climate_pave` 全传，先判断可复用分区。大图 checkpoint 尽量留远程，回传 Parquet 摘要/必要路径边表；传输包内有清单与哈希。远程任务需固定线程数防止过度并行、内存峰值、可重试分片、读写只在远程高速目录。云同步目录只作归档/交换，不直接当数据库或临时盘。
