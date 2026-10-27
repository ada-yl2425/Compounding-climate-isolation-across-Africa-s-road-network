# 重算 checklist：医疗设施数据依赖拆分（2026-10-27）

本表只安排顺序，**没有执行新的科学计算**。原稿使用的 `RAW/Health_data/{country}_health.csv` 原件修复失败后，用户已选择 iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/` 的 GPKG 提取 CSV 作为永久**重建版设施坐标输入**；后续按国从单表筛选到运行 scratch，不在 iCloud 复制 50 份。**WorldPop 人口栅格不是医疗设施数据**，缺失时仍会阻断人口加权的瓶颈、铺装和医疗结果。正式分析排除用户确认缺数据的 WestSahara。每项完整口径、代码、方法和输出字段以 [RECALCULATION_CHECKLIST.md](RECALCULATION_CHECKLIST.md) 为准，核验证据见 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md)。

## 1. 不需要医疗设施逐点表的任务

| 项目 | 可做的正式工作（待各自上游闸门通过） | 仍需的关键输入/先决条件 | 预期主结果 |
|---|---|---|---|
| [ ] C00 道路/ID | 核道路身份、长度、路面、速度匹配，建立稳定边 ID | 官方道路 RAR；旧速度表仅作对照；解压后审查 49/50 国及过滤顺序 | `canonical_roads.parquet`/GeoParquet、`road_join_audit.csv` |
| [ ] C01 模型语义 | HDM-4、MGD、IRI 上下限、月步长、降水单位、通过率重复惩罚的代码/论文审计与单元测试 | 论文/SI/代码；正式决定需道路坡度/曲率来源、CORDEX 元数据 | `model_spec.yaml`、`model_audit.md`、测试用例 CSV |
| [ ] C02 道路 IRI/速度（条件触发） | 如 C01 发现实算模型有错，重算基准/未来路段权重 | C00/C01；相应 CORDEX `pr/mrso`、道路及坡度/曲率；时窗与日历先锁定 | 分区 `road_speed_corrected/*.parquet`、QC CSV |
| [ ] C03 **非医疗**道路图/网络指标 | 统一正常/极端图权重，国别/泛非效率、连通、城市 OD | C00/C01；若触发 C02 则等其新速度；Natural Earth/既有城市节点须核源 | `edges.parquet`、`city_od.parquet`、网络摘要 CSV |
| [ ] C04 **城市 OD** 固定路线/重选路 | 分解城市对旅行时间的路段暴露与绕路缓冲 | C03 的同一图、固定 OD 和权重；旧 OD 摘要无法恢复固定路径 | `route_decomposition.parquet`、国家摘要 CSV |
| [ ] C10 NI/CV/复合排序 | 在非医疗瓶颈图上重算重要性及脆弱性 | C03；**WorldPop 正式人口栅格**和需求节点规则；边 ID | `edge_scores.parquet`、排名 CSV |
| [ ] C11 0.1%/1% 道路长度 | 汇总入选物理路段条数、总 km、均值/中位数 | C10 排名和含 `canonical_edge_id,length_km` 的边表；**此时只需表** | `intervention_length_summary.csv`、选边 Parquet |
| [ ] C12 铺装恢复与随机重复 | 同预算策略和独立随机种子比较 | C10/C11 的正确排序、C03 图和同一**WorldPop**需求/权重；旧 5 次随机摘要不够 | `paving_trials.parquet`、恢复/区间 CSV |
| [ ] C13 未来 NI-only/CV/复合排名（可选） | 同一稳定边集合跨时期比较 | C10 基准边分数、C02 未来边权；未来时窗/成员与 ID 先核 | `future_edge_scores.parquet`、稳定性 CSV |
| [ ] C15 的非医疗部分 | HDM-4、气候、铺装、路网假设敏感性及相应事件核验 | 分析所需 C00–C13 新结果；外部验证另需独立观测 | 敏感性设计 YAML、结果 Parquet/CSV |
| [ ] C16 的非医疗数值 | 先建立道路速度、网络、OD、瓶颈、干预等 claim→源表映射 | 稿件/SI、旧表可先追源；最终数值需以上正式 run_id | `claim_registry.csv`、`consistency_audit.csv` |

**重要分界**：C10–C12 不需要医院/诊所坐标，但代码 `bottleneck_network.py` 从 `RAW/Pop_data` 取 WorldPop 人口形成需求节点。因此“缺医疗设施”不是它们当前唯一的阻碍。C03/C04 指城市道路网络分析，不含医疗最短路径；后者在 C06/C08。

## 2. 涉及医疗结论的任务（设施重建输入已归档，其他闸门仍待核）

| 项目 | 已有输入可先做什么 | 正式结果仍需什么 | 暂存/最终格式 |
|---|---|---|---|
| [ ] C05 人口分母与排除 | 核 WorldPop/GADM 版本，构建像素→国界/道路/LCC 距离和“超道路 snap 阈值”等**道路侧**排除原因；检查 25/50/100 km 规则 | 永久重建设施 CSV 已可用；仍需冻结 49 国边界/人口、设施 snap、C03 校正医疗图，才能判断设施侧排除及总覆盖率 | 前处理像素分区 Parquet；正式 `coverage_denominators.csv`、排除空间 GeoParquet/GPKG |
| [ ] C06 医疗可达性/公平 | 先统一人口加权 Gini、PWMTT、等时覆盖公式，写小样本单元测试；旧节点 CSV 仅供旧口径诊断 | 已核验的重建设施坐标、WorldPop 人口总量/版本、C03 新图、C05 统一纳入样本与 49 国筛选；才能重跑时间与公平指标 | 最终 `health_node_access.parquet`、医疗摘要 CSV |
| [ ] C07 TGR/P50/P90 | **现在可用旧节点/汇总表核对旧数字的两种定义**，建指标字典与分母账本；不需要设施原件 | 正式修订值须等 C06 新节点表、同一分析人口；旧表统计不能当成修正版结论 | `metric_dictionary.yaml`；最终 `tgr_country.csv`/跨国 CSV |
| [ ] C08 医疗固定路径 | 先审计现有算法、设施多源最短路和路径保存逻辑 | 重建设施锚点、C03 医疗图、C05 人口映射；旧国别汇总不能恢复逐节点固定路径 | 最终节点分解 Parquet、国别/泛非 CSV |
| [ ] C09 设施密度/次国家相关（条件） | 可查旧回归表的定义、代码和 World Bank/GADM 版本，不重命名为新结果 | C05/C06 新节点与设施点、边界、GDP/人口源；否则只能报告旧模型 | 最终网格 GeoParquet/CSV、回归 CSV |
| [ ] C14 铺装改善医疗公平（条件） | 先锁定政策假设、同图边 ID 和干预方案；或决定收紧正文结论 | C05/C06 医疗基础结果和 C11 干预边清单；需新增医疗重算模块 | 最终节点 Parquet、效果 CSV |
| [ ] C15 的医疗部分 | 先预设设施类型、snap 半径、人口阈值敏感性口径 | 经核源设施点、WorldPop、C05/C06；旧 proxy 表只作旧口径参考 | 设计 YAML；正式结果 Parquet/CSV |
| [ ] C16 的医疗数值 | 先把 3.6、S7–S9、88.0%/81.7% 等声明映射到旧源文件并标“待替换” | C05–C09、必要时 C14/C15 正式结果；旧新版本不能混用 | 更新 `claim_registry.csv` 和一致性审计 CSV |

## 3. 当前建议执行顺序（不启动新运算）

1. **可立即做只读/口径工作**：C00 文件与 ID 审计、C01 模型定义、C07 旧 TGR 数字溯源、C11 所需边长/ID 是否在旧表中的核查、C16 旧声明来源登记。这些都不产出新的论文科学指标。
2. **优先解除非医疗阻断**：确认坡度/曲率实际使用与生成链；核实 WorldPop、Natural Earth、GADM 的论文版本；冻结 CORDEX 10 年/代码 11 年窗口和通行率定义。原始道路和气候候选在 iCloud，但“在场”不等于方法已通过。
3. **先行非医疗正式链**：通过闸门后按 C00→C01→（必要时 C02）→C03→C04/C10→C11/C12/C13。它独立于医疗设施找回，但 C10/C12 仍受 WorldPop 阻断。
4. **医疗链**：永久重建设施 CSV 已获用户采纳，原抓取日期/OSM ID 不可恢复；先冻结 WorldPop/边界、49 国选择及设施类型/snap 规则，再 C05→C06→C07/C08/C09→（若保留政策主张则 C14）→C15/C16。

最新状态：WorldPop 53 张 TIFF、GADM v4.1 全球 ZIP 和 Africa L2 工作集已从 U 盘复制到 iCloud 并逐文件核对 SHA-256，但仍需下载版本/人口总量/边界导出核源，且 iCloud 服务器端上传尚未独立确认。旧 `health_facility_pw_delta_t.gpkg` 的 87,118 行设施坐标已逐点核验并**移动**至上述永久目录；50 国档案保全，正式 49 国分析排除 WestSahara。设施原始 OSM ID、查询和日期不可恢复，方法中须说明。旧 WestSahara 医疗结果的 `pop=1` 为占位、不可用；旧 `health_accessibility_future.zip/present` 与旧基准样本冲突、不可混用。不要用旧 `experiment_state.pkl` 冒充已校正的正式图。
