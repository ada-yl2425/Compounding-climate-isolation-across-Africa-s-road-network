# Reviewer 计算核验、补算与条件重算 checklist

## 当前放行判定：2026-10-28，按用户要求简化

- **地形输入放行**：沿用用户确认的 iCloud `africa_slope_1km.tif`，按旧仓 `slope_deg` 解释为度，进入模型时 `tan(radians(slope_deg))*100`；曲率沿用道路折线累计绝对转角/公里。记录文件 SHA 与单位解释即可，不再要求恢复导出记录或重新下载。读取中遇到明确无效值才记录处理，不把真实零坡度当缺失。
- **城市吸附放行**：用户明确忽略 Kenya 最大约 109 km 吸附距离；沿用当前城市和吸附规则，该值仅记录，不阻断计算。
- **气候与道路输入放行**：16 项正式 NC 已验；49 国旧速度审计 48 国通过，Tanzania 唯一异常为 `Tanzania_road_27675` 空/无效几何在旧表多一行。正式新道路/速度计算剔除该无效几何并保留排除记录，无需追加全国家检查。
- **医疗输入预处理放行**：Djibouti 与 Benin 已通过人口守恒及距离抽样复核；使用现有 WorldPop、GADM 和永久重建设施表。正式医疗计算仍须按新图生成纳入/排除标记，属于计算实现，不追加输入实验。
- **固定路线实现尚需修正**：泛非两国试跑的 `Benin_road_0` 缺速错误，来自全道路图与仅非铺装速度表的连接口径尚未完整表达；需保留明确的铺装道路气候中性默认规则与来源映射，再运行正式任务。正常路径锁物理 road_id；合成跨境边保持同情景权重，合法零距离连接需显式处理。
- **干预实现尚需修正**：桥/渗流/铺装按具体物理 road_id 处理平行道路、保留长度，并重新投影最短权重。该工作是已发现错误的修复，不扩大检查实验。
- **统计口径直接冻结**：TGR 分位比与基准可达性群组比另名保存；零分母记不可定义并报告数量，不填 1；OD 的均值百分比与均值时间变化分开保存；随机干预逐次保存种子与恢复率。正式值基于新节点/新图重算。

**执行结论**：不再增加审计实验；可开始地形属性生成与 C02 新速度重算。OD/医疗/干预在各自上述必要代码修复完成后顺序接入。已有试算不能充当补地形后的正式修订值。

状态：2026-10-27；当前执行分支：`recalc/00-foundation`。本清单只收录涉及**计算结果核验、补算、或发现错误后重算**的审稿意见，不含纯写作、文献或绘图任务。英文引句逐字摘自用户在对话中提供的 Reviewer 1–3 / Nexus Editor 意见；同一条意见只摘录与计算有关的句子，并以原编号定位，非全文转录。`[ ]` 表示**审稿计算验证尚未完成**，不是认定原结果错误。输入文件核验和旧结果分级见 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md)；用户已确认 WestSahara 缺数据、无正式结果，正式范围为 49 国。旧 GPKG 提取表已被采纳为永久**重建版设施坐标输入**，不等于原始 OSM 文件或修订版医疗结果。详细算法、代码范围、输入层级和输出格式见 [RECALCULATION_CHECKLIST.md](RECALCULATION_CHECKLIST.md) 的 C00–C16。

统一填写规则：每项的“验证结果”应填 `通过 / 仅文字错误 / 口径错误需重算 / 数据不足 / 不适用`，附证据文件、运行 ID、代码提交、输入哈希、样本量、数值及差异；不能只写“已检查”。**本文件不启动任何新科学运算。**

## 01 模型定义、气候输入与道路速度：先核查，再决定是否整链重算

- [ ] **性质**：必做口径与实现审计；只有代码/正式输入错误才触发道路 IRI/速度、网络、医疗、瓶颈与干预的下游重算（C00–C03，必要时 C05–C14）。
- **Reviewer 1，必需 6 原文**：“The definitions, units, and time scale of several key HDM-4 parameters should be verified, particularly the definition and unit of MGD and the specific interpretation and computational implementation of the time step used in the monthly iteration.”
- **Reviewer 1，次要 6 原文**：“Supplementary Table S2 describes IRImax = 12.0 as a \"Maximum roughness cap,\" whereas Eq. 1 uses max(..., 12.0), for which 12.0 is mathematically a lower bound rather than an upper cap. The consistency among the equation, table heading, and computational implementation should be checked.”
- **Reviewer 2，次要 3 原文**：“The description of \"high-resolution CMIP6 climate projections\" in the Introduction appears not to be fully consistent with the CORDEX AFR-44, MPI-M-MPI-ESM-LR, MIROC5, and RCP4.5 data described in the Methods. Please verify and harmonize the terminology.”
- **Reviewer 2，次要 2 原文**：“The \"extreme weather\" scenario is constructed from high-percentile precipitation and soil-moisture conditions. It may be clearer to describe it as a standardized high-climate-stress scenario rather than as a single continent-wide extreme-weather event.” 此项本身是场景措辞，但先用代码/输入核对高分位构造，不据此单独重算。
- **Nexus Editor 40、42–43 原文**：“Please use SI units consistently throughout the manuscript.” “Clearly address the uncertainty associated with input data, assumptions, and model parameters where relevant.” “Ensure that all assumptions are transparent and properly justified.”
- **需验证的数据**：主文/SI 的 HDM 公式与 S2；CORDEX 月度 NetCDF 的变量、单位、日历、模型/RCP、时窗、原始来源及文件哈希；道路原始几何/路面/稳定 ID；坡度和曲率的实际生成表及 SRTM 来源；旧/未来速度 CSV 的 `IRI,V_normal,V_extreme,passable_rate,p_block`。特别核查 `MGD=0.5` 单位、`HDM4_DT=1/12` × 12 轮、月降水乘 30 天、12.0 是上/下限、缺少坡度/曲率时置零、有效速度与 `p_block` 是否重复惩罚。iCloud CORDEX 包和 U 盘道路是候选，旧 TerraClimate 中间表不等于投稿 CORDEX 输入。
- **输入核验进展**：iCloud 30 个 CORDEX NC 已 30/30 哈希/格式通过，15 对 `pr/mrso` 逐月格点相符；实际月份 28–31 天，而代码统一乘 30 天。代码先聚合 120 个月后将单个值循环 12 次；未来默认窗口包含 11 年。新增原式核查：[Paterson（TRB, 1991）](https://onlinepubs.trb.org/Onlinepubs/trr/1991/1291vol1/1291-056.pdf) 定义 MGD 为无量纲 dust ratio，指数时间 `T` 为两次平整养护之间的天数；投稿代码把 `1/12` 直接代入相同系数，存在明确量纲冲突，待确定采用的正式模型版本和维护假设。Kenya 原始道路 RAR 的 504,366 条几何没有坡度/曲率字段，四条抽样路段的 ID、长度、中心点与旧速度表精确对应；旧运行如直接用此包就会补零，仍待核实际运行日志。见 [MODEL_GATE_FINDINGS_2026-10-27.md](MODEL_GATE_FINDINGS_2026-10-27.md)。故“文件可用”不等于“旧模型正确”，正式重算和本项验证结果仍待填。
- **C00 新证据（不勾选本条）**：Kenya 原始道路→旧速度表全量 401,965/401,965 行对齐已 PASS，但旧 `network_pipeline.py` 的图边在筛选后重编号；同源顺序下预计 305,759/358,791 条候选图边误接别的源道路速度、53,031 条回退默认，只有 1 条接对。见 [KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md](KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md)。这是代码逻辑诊断而非历史 checkpoint/OD 的实测差值；五条旧图构建器已前移 ID 赋值并通过 cx3 三道路微图测试，尚待全 Kenya 端到端确认。即便 HDM 参数最终只需文字更正，该图 join 缺陷也会独立触发受影响的下游重算。
- **代码位置**：`data_procession/compute_road_speed.py:93-127,198-265,267-370`；`data_procession/future_road_speed.py:55-137,292-338`；`sensitivity/hdm4_sensitivity.py:20,81-185`；下游图权重 `result1/network_pipeline.py:138-259`、`result1/run_africa_layer.py:173-260`、`data_procession/compute_health_accessibility.py:181-253`、`data_procession/bottleneck_network.py:181-253`。旧仓 `origin/new_conclusion_1:data_procession/compute_road_loss.py:129-171` 只供曲率/坡度生成线索，气候模型并非投稿版。
- **核验/补算产物**：`model_spec.yaml`、单位与边界测试 CSV、输入/路段 ID 审计 CSV；若触发重算，分国/场景路段 Parquet 和旧新差异 CSV，之后按依赖重算。纯正文/S2 标签错误不自动触发重算。
- **验证结果（待填）**：结论＿＿；证据/输入版本＿＿；受影响下游＿＿；是否触发重算＿＿。

## 02 3.67–4.47 倍“网络放大”：固定路径与重选路对照

- [ ] **性质**：必做补算/结果重核（C03–C04）；医疗路径缓冲若保留对应解释，则 C08 同步核查。
- **Reviewer 1，必需 1 原文**：“Because these two quantities are based on different weighting schemes, the ratio may reflect both heterogeneity in road deterioration and differences in path exposure. The authors should clarify how this metric distinguishes direct path degradation from network-mediated effects. If the relevant intermediate outputs are already available, a simple comparison between baseline-path and rerouted-path results would help support this interpretation.”
- **Reviewer 2，必需 3 原文**：“The reported 3.67-4.47-fold amplification in the main text also differs conceptually from the amplification ratio defined using network efficiency in the Methods. I suggest harmonizing these definitions and distinguishing more clearly between spatial heterogeneity in road deterioration and additional system-level effects arising from network structure.”
- **Reviewer 3，必需 3 原文**：“A benchmark that holds routes fixed or otherwise isolates the contribution of network topology would help clarify the underlying mechanism and provide stronger support for the interpretation of the results.”
- **需验证的数据**：同一城市 OD 集、人口/OD 权重、路段长度、正常与极端边权、旧图与路段 ID、旧 `t0/t1` 表；逐 OD 正常路径的边序列及路径上实际速度/时间加权劣化。旧 OD CSV 只有端点旅行时间，没有可靠固定路径边序列，不能从摘要倒推。
- **代码位置**：`result1/network_pipeline.py:779-964`；`result1/run_africa_layer.py:424-604`；医疗方法参考 `result2/network_buffering_decomposition.py:299-545`。
- **核验/补算产物**：同 OD 的 `t0`、`t_fixed`、`t_reroute`、断连标记、路径暴露和聚合权重存 Parquet；按国及泛非同口径汇总 CSV；分别报告速度倒数关系、路径暴露、聚合差异与重选路缓冲，不先验把全部增幅归于拓扑。
- **验证结果（待填）**：OD/图版本＿＿；三种时间及分解＿＿；原倍数可否保留＿＿；证据文件＿＿。

## 03 TGR、P50/P90 与主文/SI 数值矛盾

- [ ] **性质**：必做旧数字追源与指标重聚合；若上游医疗图/人口修正，再做正式值重算（C06–C07、C16）。
- **Reviewer 1，必需 5 原文**：“In the Methods, TGR is defined as the P90/P50 ratio of the node-level travel-time-increase distribution, whereas the main text and Fig. 3 appear to compare population groups with different levels of baseline accessibility. In addition, the mean TGR is reported as 3.6 in the main text but as 10.38-18.63 in the Supplementary robustness results. The authors should harmonize the statistical definition and explain the numerical discrepancy between the main text and the Supplementary analyses.”
- **Reviewer 2，次要 10 原文**：“Please conduct a final consistency check of the main numerical values and terminology across the Abstract, Results, Methods, and Supplementary Information, particularly for amplification, TGR, and recovery metrics.”
- **需验证的数据**：逐节点 `t0,t1,Δt,pop,country`、纳入/排除规则与设施可达掩码；旧节点 CSV、S7–S8、主文 3.6 的来源；各国样本数、零/负 P50、人口权重与跨国汇总方式。区分 `Q90(Δt)/Q50(Δt)` 与按**基准可达性分组**的群体平均 `Δt` 比。
- **代码位置**：`data_procession/compute_health_accessibility.py:488-545,551-760`；`result2/inequality_deepdive.py:71-341`；`result2/network_buffering_decomposition.py:414-545`；`sensitivity/health_variant_grid_sensitivity.py:550-580`。
- **核验/补算产物**：两个分开命名的指标字典、逐国及跨国 CSV、旧数字来源/差异表；旧节点可先本地核旧口径，正式新值依赖 C05–C06。
- **验证结果（待填）**：两个定义的值＿＿；3.6 与 10.38–18.63 来源＿＿；正式值是否需重算＿＿。

## 04 医疗分析排除人口、覆盖率分母与阈值

- [ ] **性质**：必做空间/分母补算与旧结果核验（C05–C06；必要时 C09）。
- **Reviewer 1，必需 4 原文**：“Given the high exclusion rate and its cross-country variation, it is important to determine whether excluded populations are systematically concentrated in remote or poorly accessible areas, and whether this affects the reported 1-hour healthcare coverage and inequality results. The authors should clarify the population denominator used for the reported 88.0% and 81.7% coverage values and indicate whether the excluded and retained populations differ systematically in baseline accessibility.”
- **Reviewer 2，次要 7 原文**：“Coverage losses differ across the 30 min, 1 h, 2 h, and 4 h healthcare-accessibility thresholds, with the largest decline at the 30 min threshold. This pattern deserves brief discussion in relation to the inequality results.”
- **需验证的数据**：2020 WorldPop 原始人口栅格、GADM 国界、规范化道路和 LCC、永久 GPKG 重建设施坐标、设施/人口 snap 距离、25/50/100 km 规则；旧 S9 排除比例与四个等时阈值表。原始 OSM CSV 修复失败，87,118 行提取表已经逐点核验但缺抓取日期/OSM ID；正式 49 国剔除 ESH 旧占位医疗结果，不虚构该地区人口与可达性。
- **代码位置**：`data_procession/compute_health_accessibility.py:257-394,488-545,551-760`；`sensitivity/health_variant_grid_sensitivity.py:172-349`；`sensitivity/health_access_sensitivity.py`；`result2/isochrone_analysis.py`。`compute_health_accessibility.py:606-610` 的缺栅格 `pop=1` 回退必须审计。
- **核验/补算产物**：逐像素/节点 `population_assignment.parquet` 含距离和排除原因；国家人口分母与 30 min/1/2/4 h 覆盖 CSV；排除人口空间 GeoParquet/GPKG；25/50/100 km 敏感性。网络不可接入者不虚构旅行时间。
- **验证结果（待填）**：88.0%/81.7% 分母＿＿；各国排除原因/距离＿＿；阈值敏感性＿＿；结论影响＿＿。

## 05 0.1%/1% 干预的道路长度与预算定义

- [ ] **性质**：必做长度统计；若排序/图修正，则与 C10–C12 同步重算。
- **Reviewer 1，次要 1 原文**：“The 0.1% intervention is currently expressed as approximately 767 graph edges. Because the number of edges depends on GIS segmentation, the corresponding total road length and the mean or median length of the selected edges should also be reported.”
- **Reviewer 2，必需 2 原文**：“However, the reported 0.1% intervention is defined in terms of graph edges rather than road length or investment cost, and the modeled \"paving\" operation is closer to an idealized restoration of road performance.”
- **需验证的数据**：0.1% 与 1% 的实际入选 graph-edge ID、可干预边总数/取整规则、每条边 `length_km`、原道路物理段/合并边映射、排序/预算。旧全边 NI/CV 表没有可确认的一对一原道路 ID/长度，仅凭它不能安全汇总 767 条 km。
- **代码位置**：`result3/paving_experiment.py:61-137`；`data_procession/bottleneck_network.py:447-565`；图边构造 `result1/network_pipeline.py:104-259`。
- **核验/补算产物**：稳定 ID 的入选清单 Parquet、0.1%/1% 总 km/均值/中位数/范围 CSV；区分“按边数预算”和“按公里预算”，不估称投资成本。有带稳定 ID 与长度的正确表后可本地完成，无需气候原始 NC。
- **验证结果（待填）**：767 条映射率＿＿；0.1%/1% 长度＿＿；预算定义＿＿；来源表＿＿。

## 06 NI 与 CV 对恢复率的边际贡献

- [ ] **性质**：先核现有对照，不因为审稿提问就重复相同实验；若模型/排序修正，则 C10–C12 重算。
- **Reviewer 1，必需 2 原文**：“The Supplementary results show that, at the 0.1% intervention level, the combined NI×CV strategy achieves 71.7% recovery, while NI-only already reaches 71.2%; at the 1% level, both reach 91.2%. This makes the additional contribution of climate vulnerability (CV) beyond network importance (NI) unclear.”
- **Reviewer 2，必需 2 原文**：“In addition, Supplementary Table S10 shows very similar recovery between the NI-only and combined strategies. The policy message would therefore be stronger if it were framed primarily in terms of the high network leverage of a small set of structurally important links, while more directly acknowledging the dominant role of network importance in the current results.”
- **需验证的数据**：S10、旧策略/边分数表、NI-only/NI×CV/CV-only 排序、同预算与同恢复率分母、旧图/OD 样本。旧 71.7/71.2 和 91.2/91.2 先做源表一致性检查。
- **代码位置**：`data_procession/bottleneck_network.py:447-565`；`result3/paving_experiment.py:61-137`；`sensitivity/bottleneck_recovery_sensitivity.py:150-225`。
- **核验/补算产物**：策略对照/差值及样本口径 CSV；若上游变更，重算同预算恢复实验 Parquet/CSV。
- **验证结果（待填）**：旧值与 S10 是否一致＿＿；CV 边际值＿＿；需否重算＿＿。

## 07 随机铺装重复次数与不确定性

- [ ] **性质**：若旧逐次结果不存在，必须补做独立随机重复并留逐次值（C12）。
- **Reviewer 1，次要 2 原文**：“Recovery under the 0.1% random strategy is very close to zero, making the reported approximately 1,200-fold comparison sensitive to a very small denominator. The number of random repetitions, together with the mean or median and a basic uncertainty range, should be reported.”
- **Reviewer 2，次要 9 原文**：“The approximately 1,200-fold comparison is based on a very small random-recovery denominator. Reporting the recovery rates of the alternative strategies directly may be more informative and less sensitive to this ratio.”
- **需验证的数据**：旧试验配置/种子、每次随机入选边及恢复率（如有）、旧均值/标准差、同预算/OD/指标分母。当前代码 `N_RANDOM_TRIALS=5`，旧摘要仅有均值/标准差，尚未找到逐次结果；不能从二者倒推出经验范围。
- **代码位置**：`result3/paving_experiment.py:23-137`；`sensitivity/bottleneck_recovery_sensitivity.py:32,300-350`。
- **核验/补算产物**：`paving_trials.parquet` 每次策略/预算/种子/恢复率；`random_uncertainty.csv` 次数、均值/中位数、分位/置信区间；直接报告各策略恢复率，倍数仅作为敏感指标。
- **验证结果（待填）**：旧逐次值是否存在＿＿；新重复数/区间＿＿；1,200 倍处理＿＿。

## 08 未来排名稳定性来源：固定 NI 与变化 CV

- [ ] **性质**：Reviewer 1 明说 “If feasible”，属于可行时的补算；若不做，仍需限定固定拓扑条件下的解释（C13）。
- **Reviewer 1，必需 3 原文**：“The Future Persistence analysis holds the baseline road-network geometry fixed, so part of the observed ranking stability may arise from the persistence of network structure itself. The authors should make this conditioning explicit when interpreting long-term stability and explain, based on the existing results, the respective roles of NI and climate vulnerability in cross-period stability. If feasible, a simple comparison between NI-only and combined rankings would be informative.”
- **Reviewer 2，次要 8 原文**：“Population, travel demand, and the road-network structure are largely held fixed in the future scenarios. The Discussion should clarify that these projections primarily capture climate-driven changes in road performance and prioritization rather than a full forecast of future transport systems.”
- **需验证的数据**：同一可干预边集合与稳定 ID、基准 NI、各 RCP/GCM/时段 CV 与 NI×CV、归一化规则、未来气候/速度文件及缺失率。旧未来速度包缺完整 MIROC 2085 派生结果，须与原始 NC 和实际运行清单核对。
- **代码位置**：`result3/bottleneck_stability.py:88-197,197-377`；`result3/run_bottleneck_stability.py`；`data_procession/future_road_speed.py`；`sensitivity/rcp85_future_stability.py`。
- **核验/补算产物**：逐边未来分数 Parquet，NI-only/CV-only/NI×CV 的 Spearman/Kendall/Top-k 重合与匹配 QC CSV；固定 NI 自身跨期不变不当成新证据。
- **验证结果（待填）**：场景/时段完整性＿＿；边匹配率＿＿；排名对照＿＿；是否可行＿＿。

## 09 49/50 国、多尺度节点与图中指标定义的一致性

- [ ] **性质**：必做样本/公式/数值审计；若旧数字来自不同集合且论文仍声称可比，修正口径后才对相应层重算（C03、C16）。
- **Reviewer 1，次要 3 原文**：“The numbers of countries and nodes differ across analytical layers. The Methods should provide a concise summary of the geographical units, node counts, and OD definitions used in each analysis.”
- **Reviewer 1，次要 5 原文**：“The accessibility-loss rate in Fig. 2e, the facility-level loss in Fig. 4, the population × percentage-points metric in Fig. 5d, and the normalized amplification gap in the percolation analysis should be explicitly defined in the Methods or figure captions.”
- **Reviewer 2，必需 1 原文**：“The manuscript analyzes international city pairs, within-country city pairs, and local city networks. This multi-scale design is a strength, but the node sets, metrics, and aggregation procedures are not identical across these levels. The authors should clarify what question each scale is intended to answer and which results are directly comparable.”
- **Reviewer 2，次要 5 原文**：“The use of \"49 countries\" versus 50 country folders in some data layers should be briefly explained in the Methods to avoid ambiguity regarding the geographical scope of the analysis.”
- **Nexus Editor 41 原文**：“Present all data carefully and with consistent numerical accuracy.”
- **需验证的数据**：主文/SI 每层国家、城市节点、OD 组合、过滤/连通掩码、人口、原始表与结果表；Natural Earth `ne_10m_populated_places` 原件若可找回、以及既有 Africa/country 层节点 CSV；Fig. 2e/4/5d/percolation 的逐项分子分母。旧 Africa 节点 CSV 为 84（50 首都+34 大城市），多出的已确认是 `ESH_capital/Bir Lehlou`；可用旧表按 `iso3 != ESH` 重建正式 83/49 的**节点输入**，但旧 Africa OD 汇总按 84 算且缺逐对表，不能只删 ESH 行得到正式结果。旧 country 层 801/50 包含 ESH 占位节点。现有 `africa_gadm41_level2.gpkg` 在 Kenya 有 1,442 条/300 个 `GID_2`/1,442 个 `GID_3`，不是可直接替代原 L2 Shapefile 的统一层，须从全球 GADM 源校验层级。
- **代码位置**：节点/OD `data_procession/prepare_africa_layer.py:84-180`、`data_procession/prepare_country_layer.py:82-174`、`result1/network_pipeline.py:750-964`、`result1/run_africa_layer.py:424-604`、`result1/merge_country_results.py:72-100`；效率/渗流放大 `result1/network_pipeline.py:419-538,690-745`；医疗/设施候选 `data_procession/compute_health_accessibility.py`、`result2/isochrone_analysis.py`、`result2/facility_accessibility_scatter.py:83-109`；干预候选 `result3/paving_experiment.py`、`result3/paving_isolation_analysis.py`。Fig. 2e/4/5d 的**最终绘图源表→公式**映射仍待逐图确认，不能仅凭文件名认定。
- **核验/补算产物**：`analysis_population_registry.csv`（层级/国家/节点/OD/权重/掩码）、`metric_dictionary.yaml`、`claim_to_result.csv`；需要改样本才重算相应摘要，不默认 49/50 或 83/84 可互换。
- **验证结果（待填）**：49/50 差异原因＿＿；83/84 差异原因＿＿；各图公式与源表＿＿；需重算层级＿＿。

## 10 干预对医疗可达性和公平的效益（仅保留此政策主张时）

- [ ] **性质**：二选一的条件任务（C14）：做医疗/公平干预计算，或明确收紧政策结论；审稿人没有要求必须新增这一实验。
- **Reviewer 3，必需 4 原文**：“Moreover, improving overall network efficiency does not necessarily lead to corresponding improvements in healthcare accessibility or reductions in inequality. It would strengthen the practical relevance of the study if the authors could examine whether the proposed intervention strategy remains effective under alternative objectives, particularly population-weighted healthcare accessibility and equity considerations. Alternatively, the authors may wish to qualify their policy recommendations to better reflect the assumptions and limitations of the current analysis.”
- **需验证的数据**：同一医疗图/设施点/WorldPop 人口及纳入掩码、C11 干预边 ID 与预算、干预前后医疗时间、PWMTT/覆盖率/不平等公式。旧网络效率恢复不能当医疗公平效益证据。
- **代码位置**：`result3/paving_experiment.py`、`data_procession/compute_health_accessibility.py`、`result2/isochrone_analysis.py`；目前没有完整的直接联动实现，若选择计算需新模块及边映射 QC。
- **核验/补算产物**：若选择实验，逐节点/人口干预结果 Parquet、分国/全非差值和区间 CSV；若收紧结论，记录“未声称医疗公平已改善”，不产生虚构结果。
- **验证结果（待填）**：选择计算或收紧主张＿＿；若计算，结果/样本/映射率＿＿。

## 11 跨任务输入不确定性与“验证”措辞

- [ ] **性质**：跨任务检查，按保留的结论决定是否需要附加敏感性/外部一致性分析（C15），不把泛泛编辑要求误读为必须重跑全模型。
- **Nexus Editor 42、46 原文**：“Clearly address the uncertainty associated with input data, assumptions, and model parameters where relevant.” “Where modeling is involved, provide experimental validation or other strong forms of validation whenever possible.”
- **Reviewer 1，次要 4 原文**：“These two cases primarily assess spatial consistency rather than event-level prediction. The manuscript should consistently use terms such as external plausibility check or spatial consistency check, rather than implying validation in the strict event-prediction sense.”
- **需验证的数据**：已做 HDM/气候/设施 snap/道路缺失/随机重复的敏感性实际输入、参数范围与运行日志；Idai/Kenya 观测和论文所用时空范围。旧稳健性包若只是抽样或缓存 proxy，不能称修正模型的全量重跑。
- **代码位置**：`sensitivity/hdm4_sensitivity.py`、`sensitivity/health_variant_grid_sensitivity.py`、`sensitivity/bottleneck_recovery_sensitivity.py`、`sensitivity/appendix_idai_validation.py`、`sensitivity/appendix_kenya_validation.py`。
- **核验/补算产物**：`sensitivity_design.yaml`、旧/新方法差异及区间 CSV、外部案例来源表；只在实质假设未覆盖且主张保留时增补计算。
- **验证结果（待填）**：已有分析可用范围＿＿；需新增分析＿＿；事件案例表述/证据＿＿。

## 执行闸门与填表顺序

1. 先完成 01、09 的**版本、单位、边 ID 与样本口径审计**；这一步不等于已重算。确认气候是投稿实际 CORDEX 模型/时段，曲率/坡度是否真的进入速度模型。错误触发时生成新 `run_id`，绝不覆盖旧包。
2. 与医疗设施无关的 02、05–08 可在路网和人口数据放行后先行；03 可先追旧 TGR 来源，但正式修订值要等 04 的医疗样本和权重放行。07 的随机重复不能用旧均值/标准差伪造逐次结果。
3. 04 与 10 的正式医疗结果使用已核验并永久归档的旧 GPKG 提取设施坐标表；该表是重建版历史输入，不是原始 OSM 下载，也不证明旧运行日期或去重规则。所有大型输入按阶段传输、校验哈希并在本机/远程高速盘运算，不在 U 盘直接读写输出。
4. 每项填完“验证结果”后，登记 `source file + SHA-256 + code commit + config + run_id + n countries/n edges/n OD/n people + formula + output path`；最后执行 03、09 的全稿数值一致性复核。结果大表用 Parquet/GeoParquet，小型可引用汇总用 CSV；GPKG 仅用于需要 GIS 互操作的空间交付。

**当前总状态**：11/11 项验证结果待填；已找到若干候选输入与旧结果，但没有一项因“文件存在”而自动勾选完成。

**远程工程准备（非审稿结果）**：cx3 SSH 复用会话已连通；首批 Kenya 8 个输入以 [manifest](kenya_input_manifest_2026-10-27.json) 在本地及远端双重哈希 `PASS`，远端工程测试 `8 passed`。仅完成输入传输/环境检查，不改变上面的 11/11 待填状态；G0 道路劣化模型定义和 G1 共享图边/人口/OD 口径仍需放行，正式 PBS 科学任务未启动。详情见 [远程执行计划](REMOTE_RECALC_EXECUTION_PLAN.md)。

**2026-10-28 在运行的闸门（仍非正式审稿指标）**：C00 49/49 官方道路 RAR 已传 cx3，并按官方 MD5/大小与旧速度 ZIP SHA-256 核对；远端输入 manifest 为 `PASS`，本机 iCloud 归档见 `africa pavement/05_manifests/road_speed_alignment_49_7d691fa_20261028/input_transfer_manifest.json`。Benin 与 Botswana、BurkinaFaso、Burundi、Cameroon 的逐行身份核对已 `PASS`；剩余国家由 PBS `4490533[]`、`4490534[]` 执行，终验 `4490535` 待全部完成。**不是仅用单国代替全非：正式 C00 范围为 49 国全行核对；目前不能勾选。** Kenya 旧全图 QA 发现端点传递合并、自环、平行边覆盖及 4,152 条图/表 ID 权重不一致；修复后全图工程复验 PBS `4490565` 待结果，故 C03/C04/C10–C12 尚不可批量运行。C04 固定物理道路 ID 的三时间分解模块已在 cx3 通过 3/3 微型测试，尚无真实 OD 结果。气候正式输入 16 项 NC 的成员/月份/单位/哈希已验收，Kenya 旧速度 411 段的 IRI 可用旧代码零坡度/零曲率口径重现至 <1e-5；此项说明旧表生成方式，不等于论文地形描述或修订模型已放行。正式科学重算结果仍为 **0 项**。

**启动门槛调整（用户 2026-10-28 决定）**：审稿指标试算不等 C00 的 49 国全量旧速度审计；几个代表国家的来源/公式/图完整性检查通过即可启动相应单国 pilot，已提交的 49 国审计后台继续。用户另选择 **补入地形重新建模**，因此旧零地形速度只能做历史对照及算法试运行，不能直接作为正式修订结果。C02 必须先锁定 DEM/坡度来源、曲率算法、坐标单位、缺值规则与单测，计算新速度并复核后再批量生成最终 C03–C14 指标。

**已通过／已启动（2026-10-28）**：Kenya 修复图工程 QA `4490565.pbs-7` 为 `Exit_status=0`，QC SHA-256 `e45dc30e96aa7429c4706f3ea15409dfc669197a5f90a373bc28eebefd0df324`；358,791 条物理边、133,309 条简单图路由边、98,457 节点，正常/极端图选中道路 ID 与权重错配、自环、旧速度缺配均为 0。相对旧图规模变化很大，放行**单国 OD/效率试算**而非直接认可科学效应；C10–C12 平行物理路/桥/渗流/施工边预算仍未放行。Kenya 固定物理路 C04 三时间试算 PBS `4490595.pbs-7` 已提交，使用旧速度，仅为工程与定义试算，不作为正式新模型结果。Djibouti C05 独立人口分母/设施距离 pilot `4490570.pbs-7` 通过，见 [C05 输入闸门](HEALTH_C05_PREPROCESS_GATE_2026-10-28.md)；不含路网时间和正式覆盖率。旧 C07 追源显示 Fig.3a 3.6 的绘图表有 44/49 国 P50/P90 与归档逐节点人口加权分位不一致，见 [旧 TGR 审计](LEGACY_TGR_SOURCE_AUDIT_2026-10-28.md)；因此正式 TGR 等新 C06 节点输出后重聚合。

**C10–C12 口径门禁（2026-10-28）**：旧桥边/渗流/铺装实现把平行物理道路折叠为简单图节点对，旧铺装把该 pair 的极端权重直接改正常权重，未锁定具体 `road_id`；旧 NI/实验状态亦缺 `road_id,length_km` 映射，不能把 767 条旧图边精确解释为道路条数或公里数。随机旧实现仅 5 次、只留均值/标准差。小图门禁本机和 cx3 均 5/5 通过，但结论为正式重算 **NO-GO**，详见 [物理道路干预门禁](INTERVENTION_PHYSICAL_ROAD_GATE_2026-10-28.md)。新地形速度+物理路权表稳定后须重建 C10 排名及 C11/C12 结果；不能靠旧汇总表补公里数或随机区间。

**坡度来源决策更新（用户 2026-10-28）**：用户确认 iCloud 已有的 `africa_slope_1km.tif` 是所需真实坡度，**不重新下载/导出**。当前把它用于 Benin/Kenya 地形属性试算；正式 C02 前仍需在现有 TIFF 和旧仓处理脚本上确认角度/百分比单位、有效像元/NoData、坐标与道路覆盖、抽样及 `road_id` 一对一，并明确记录“用户确认文件”与可复核代码证据的区别。不得把无效像元静默当作零坡度。
