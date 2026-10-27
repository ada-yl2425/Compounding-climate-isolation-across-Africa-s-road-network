# 审稿意见中的计算任务：现有证据与剩余闸门（2026-10-27）

范围仅限需要核查计算结果、可能补算/重算的意见；不把措辞、文献、图示或政策讨论本身列成计算任务。Reviewer 1/2/3 英文原文由用户在本次对话中提供；下列为对应原文的**定位性短语/要求摘要**，不是完整逐字引文。逐项原文摘录和待填验证栏见 [REVIEWER_RECALCULATION_CHECKLIST.md](REVIEWER_RECALCULATION_CHECKLIST.md)；本轮数据核对结果与 49 国正式范围见 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md)；完整技术执行规范见 [RECALCULATION_CHECKLIST.md](RECALCULATION_CHECKLIST.md)。截至本日没有执行新的论文科学运算，也没有核准任何旧结果为修订版正式结果。

| 审稿原文定位（条号） | 必要计算决定 | 现有可复用证据 | 尚未确认/下一闸门 |
|---|---|---|---|
| R1 必需 6 “MGD ... time step used in the monthly iteration”；R1 次要 6 `IRImax=12.0` 与 `max(...,12.0)` | C00–C01 审计，只有实算错误才触发 C02 及 C03–C14 受影响下游重算 | 主文、SI、`compute_road_speed.py`、旧速度 ZIP、CORDEX 候选 | MGD 原定义/单位；30 天月雨量与 NC 日历；`HDM4_DT=1/12` × 12 的物理含义；12.0 上/下限；通行概率是否重复计入；实际曲率/坡度字段和运行版本。**不能从文稿矛盾直接认定代码错。** |
| R1 必需 1 “baseline-path and rerouted-path”；R2 必需 3 区分劣化/路径暴露/结构；R3 必需 3 “benchmark that holds routes fixed” | C03–C04 同 OD、同权重得到 `t0,t_fixed,t_reroute`；必要时 C08 医疗路径。纠正 3.67–4.47 倍的机制归因 | 旧 OD CSV 只存 `t0,t1`，医疗缓冲旧国家汇总可审计定义 | 旧包无足够逐路径边表；固定路径必须用通过 C00–C03 的图重建。可报告绕路缓冲，但不可先验把总增长称拓扑放大 |
| R1 必需 5 “P90/P50 ... node-level travel-time-increase” vs 基准可达性人群，3.6 vs 10.38–18.63；R2 次要 10 最终数字一致性 | C07 把两种指标拆名、核样本/权重/跨国聚合；C16 更新 claim→结果账本 | 旧节点和汇总 CSV 可本地重算**旧口径**统计来源，不需要设施原始表 | 正式修订值若依赖更正的图/人口，必须等待 C05–C06；不可为了相等而改数 |
| R1 必需 4 “population exclusion ... concentrated in remote ... denominator ... 88.0% and 81.7%” | C05–C06 逐像素/节点排除原因与空间差异、25/50/100 km 和覆盖/不平等分母 | U 盘 WorldPop 与 GADM 已哈希复制到 iCloud；旧 S9/稳健性只作旧口径参照；旧 GPKG 提出设施候选坐标 | WorldPop/边界与正式版本及国家掩膜、设施原件/去重、路网 LCC/snap 核源；旧 100k 抽样 proxy 不能给全人口排除空间分布 |
| R1 次要 1 “total road length and mean or median length” of 0.1%；R2 必需 2 对 graph edges/km/cost 的界限 | C11 从同一入选边名单和稳定边长求 0.1%/1% km；不把 km 称为成本 | 旧结果证实 0.1% 约 767 graph edges；旧分数 CSV 无原道路 ID/长度 | 需 C00/C10 图边—原道路段映射；一旦有含 `edge_id,length_km,rank` 的表，本地仅表即可 |
| R1 次要 2 “number of random repetitions ... mean or median ... uncertainty range”；R2 次要 9 提醒约 1,200 倍分母过小 | C12 随机试验逐次结果及不确定性；如保留策略比较，修正图上同预算比较 | 旧代码为 5 次；旧摘要含随机恢复率均值/标准差，但没有 5 次逐次结果 | 可注明旧 5 次做法，却不能从均值/标准差反推经验范围；正式区间/改模型后比较需独立重复并存每次结果 |
| R1 必需 3 “If feasible ... NI-only and combined rankings” | C13 是**可行时补算**，固定 NI/变化 CV 在同一边集比较；若不做也须据现有结果限定解释 | 旧全边 NI/CV 表与未来速度/排名候选可用于旧口径探查 | 稳定边 ID、未来时段和缺失 MIROC 2085 输出；不能把固定 NI 的自身不变当新证据 |
| R1 必需 2 NI-only 71.2% vs NI×CV 71.7%、1% 都 91.2%；R2 必需 2 同类意见 | **先核旧表和说明 CV 的边际贡献，不自动新增同一策略重算**；若 C01–C03 修正影响排序/恢复则随 C10–C12 重算 | 旧策略摘要可复核数字和旧代码口径 | 旧边 ID/预算定义，以及模型审计是否触发整链修正 |
| R3 必需 4 “examine ... healthcare accessibility and equity ... Alternatively ... qualify policy recommendations” | C14 **条件任务**：若保留医疗公平效益的政策主张，须在医疗图重跑；选择收紧主张则无需此新增计算 | 现有实验主要是网络效率恢复，不足以推出医疗公平改善 | 用户/稿件最终政策表述；若计算，需 C05–C06 设施/人口图和 C11 干预边映射 |

另须计算口径核对而非独立大型重算：R1 次要 3 与 R2 必需 1/次要 5 要解释 49/50 国、83/84 城市节点、801 国别节点及多尺度 OD 可比性。用户已确认 WestSahara 缺数据、无正式结果；旧 84 个 Africa 节点比主文/SI 83 个多 `ESH_capital/Bir Lehlou`，且旧孤立表按 84 节点计算。旧包无逐 OD Africa 表，不能只删 ESH 一行就精确得到 83 节点结果；是否让 ESH 道路仅作过境还需定口径。R2 次要 3 的 CMIP6/CORDEX 用词不一致属于气候输入溯源核对；30 个 CORDEX NC 已验证内部一致，但不能因此认定旧速度输出使用相同文件/时窗。

## 数据恢复和版本界线

- U 盘 `/Volumes/GALACTIC/非洲道路proj/WorldPop/` 的 53 张 `*_ppp_2020_UNadj_constrained.tif`、`GADM边界.zip`（内含全球 GADM 4.1 GPKG）和 `africa_gadm41_level2.gpkg` 已复制至 iCloud `africa pavement/01_sources/`、`02_derived_checkpoints/boundaries/` 并逐文件哈希比对。Africa L2 文件只有 53 ISO 且缺 ESH；全球 ZIP 含 ESH。未额外复制解压后的约 2.6 GB 全球 GPKG，避免重复占本机磁盘。iCloud 云端上传状态仍待确认；没有删除 U 盘源。
- 旧 iCloud `中间数据/health_facility_pw_delta_t.gpkg` 有 87,118 个点、50 国；逐点几何/经纬度与导出 CSV 一致，逐国数目与旧 `country_accessibility_summary.csv` 50/50 对应。原医疗 CSV 修复失败后，用户已决定永久采用该重建坐标集，现位于 iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/`，含 README/manifest。12,734 条原本无名称保留，正式 49 国运行排除 WestSahara。**这不是原始 OSM 下载，仍无法恢复 OSM ID/查询日期/原去重规则。**
- 老仓 `africa-road-climate-accessibility` 的 `origin/new_conclusion_1` 版本 `data_procession/compute_road_loss.py` 从投影线段方位角转折/公里生成 `curvature_deg_km`，从 SRTM 衍生 raster 于路段质心取坡度。主文也提这条来源；当前仓 `compute_road_speed.py` 却仅消费 `curvature_deg_km,slope_deg`，缺字段即置零。U 盘 50 国原道路 DBF 只有 `ID,Start_pt,End_pt,Rd_length,Surface`；旧仓的整套气候/IRI 模型与投稿 CORDEX 方案不同，**只可借用几何计算思路，不能把旧结果直接替代正式速度。**
- 老仓城市代码指向 Natural Earth `ne_10m_populated_places.shp`；已审 U 盘未见原件。旧 iCloud 84/801 节点表可作节点/ID 历史证据，不等于下载源和筛选规则完整。旧 `result.zip` 有 NI/CV 和 `t0,t1`，但无可靠长度映射或固定路边序列；旧 `robustness_outputs.zip` 部分医疗结果是抽样/proxy；旧 `health_accessibility_future.zip` 的“present”与另一旧基准包样本/指标冲突，禁止混合。

## 对正式重跑仍未放行的依赖

1. **方法版本**：C00 道路稳定键/路速 join；C01 的 MGD、IRI 界限、月步长、降水单位、坡度/曲率、`passable_rate` 双重惩罚，决定 C02 是否触发。
2. **气候与地形**：逐个 NetCDF 确认变量、RCM/GCM/RCP、时间窗、日历/单位、完整性和最终旧运行参数；坡度源 raster、曲率实现和最终路段字段/ID 尚未闭环。旧 TerraClimate 2020–25 中间表不等于投稿 CORDEX 2011–20；旧未来速度 ZIP 缺 MIROC 2085 派生结果。
3. **道路/空间和医疗**：WorldPop/GADM 候选与投稿实际人口总量和边界导出比对；Natural Earth 原始点及 83/84 筛选；用户确认的 WestSahara 正式排除与 ESH 路段过境规则。重建设施坐标集已核验和采纳，但其原始抓取日期不可恢复；医疗正式结果仍取决于图权重/人口/样本审定。
4. **旧结果边界**：可本地追溯旧 TGR、NI/CV、随机试验摘要、医疗设施点；不能从国别汇总倒推固定路径、全量排除像素、767 条边长度或随机试验逐次值。校正的正式结果必须保留 `run_id`、输入哈希、代码提交、配置、随机种子和 Parquet/CSV/GPKG 分层产物。

本次仅整理/迁移/导出候选数据和审计；没有运行 C02–C16 的科学分析。旧资料与新结果一律分开存放，不覆盖、不先删，待云端同步及版本核准后再讨论清理。
