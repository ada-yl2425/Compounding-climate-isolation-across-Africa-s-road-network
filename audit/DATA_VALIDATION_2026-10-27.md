# 审稿重算数据核对与输入放行记录（2026-10-27）

核对范围：当前稿件/SI、当前及旧代码、U 盘、iCloud 原始/中间/结果档。此文件记录**可验证到的事实与不能确认的血缘**，不表示已执行审稿要求的网络、医疗或干预科学重算。用户已明确 WestSahara 数据缺失、无正式结果；正式结果集合为 49 国，历史档案仍保留其记录以便溯源。原文要求和待填科学结果见 [REVIEWER_RECALCULATION_CHECKLIST.md](REVIEWER_RECALCULATION_CHECKLIST.md)。

## 已核对的输入和用途

| 数据层 | 已核对证据 | 本轮决定 | 未解决的限制 |
|---|---|---|---|
| FRST 道路源 | iCloud `01_sources/roads/FRST_figshare_29424107_v1/` 50 个 RAR 与 Figshare v1 MD5 清单一致，见 `FRST_FIGSHARE_VERIFICATION.csv`；U 盘 50 国 DBF 共 13,309,613 行，字段统一为 `ID,Start_pt,End_pt,Rd_length,Surface`；抽样 Kenya 的 SHP/DBF 与官方 RAR 内对应文件 SHA-256 完全一致 | RAR 可作官方道路原始源；DBF/几何可作处理候选，正式国别结果剔除 WestSahara | 其余 49 国未逐一解包字节比对，必须审计道路行 ID/过滤/几何→速度 CSV 的匹配；DBF **无 `slope_deg`/`curvature_deg_km`**，当前速度代码缺字段默默置 0；缺最终旧运行链 |
| CORDEX 月度气候 | iCloud `01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1/` 30 个 NC 与现有 SHA 清单 30/30 一致、都可读；15 对 `pr/mrso` 的 time/格点匹配，每文件 120 连续月、201×194 格点；MPI rcp45 7 对、MIROC rcp45 6 对、MPI rcp85 2 对 | 文件是投稿描述的 AFR-44/SMHI-RCA4/MPI/MIROC/RCP 场景**可用重算候选**；包含补算 MIROC 2085 所需原始数据 | 无原下载 dataset ID/官方哈希或旧日志，不能证明旧速度 CSV 由这 30 个文件产生；旧速度未来仅 6 组，缺 MIROC 2085 |
| CORDEX 单位/时间 | `pr` 为 `kg m-2 s-1` 的 time mean，`mrso` 为 `kg m-2`；MPI calendar `proleptic_gregorian`、MIROC `365_day`；实际月界 28–31 天 | 需按 NC `time_bnds`/日历处理月长并冻结时间窗后才可正式计算 | 当前代码固定 `pr×86400×30`；2011–20 实际 3653 天而固定 30 天×120 为 3600 天。代码还先把 120 个月汇成均值/P95，再以同一常数循环 12 次；未来默认 `period±5` 读 11 年，与稿件十年窗不一致。这是**代码/稿件口径冲突**，旧结果能否保留尚未判定 |
| WorldPop | U 盘 53 张 `*_ppp_2020_UNadj_constrained.tif` 与 iCloud `01_sources/population/WorldPop_2020_UNadj_constrained_candidate/` 逐文件 SHA 一致；文件为 EPSG:4326、约 0.000833°、Float32/LZW、NoData −99999；53 个 ISO 与 Africa L2 边界集合完全相同，覆盖正式 49 道路国，另有 4 个非正式研究 ISO；无 ESH。Kenya 源/副本 SHA 为 `bf775d71507bf375f14afb316dbdaa0f13fb3d7bff5f3e3d0139591b2706b8d2` | 可作正式 49 国人口计算的**待核源候选**，不应用代码 `pop=1` 回退填补 WestSahara | 缺原下载记录/官方版本哈希及逐国人口总量与论文最终旧运行比对；不能仅因文件名相符便声称旧结论使用它们 |
| GADM 边界 | U 盘全球 `GADM边界.zip`（内含 `gadm_410.gpkg`）与 iCloud ZIP SHA 一致；所谓 Africa L2 工作集 `africa_gadm41_level2.gpkg` 源/副本 SHA 一致，56,680 行/53 ISO；全球源含 ESH，而工作集无 ESH。新增字段检查：Kenya 1,442 行却只有 300 个 `GID_2`、1,442 个非空 `GID_3`；整个工作集仅 6,476 个 `GID_2`，因此文件名**不能证明其为统一 L2 几何** | ZIP 保存全球 GADM 4.1 原件；现有 Africa 工作集只作为最细行政记录候选，不得直接传入期待 `_2.shp` 的代码 | 先做 Kenya 原始 L1/L2 图层与按 `GID_1/GID_2` dissolve 的 ID、面积、对称差比对，再生成统一按层级的工作集；云端上传尚未独立证实 |
| 地形/曲率 | 旧仓 `origin/new_conclusion_1:data_procession/compute_road_loss.py:129-171` 从投影几何方位转角/公里求 `curvature_deg_km`，SRTM 衍生坡度 raster 于路段质心抽取；主文也提几何曲率和 SRTM 坡度。iCloud `01_sources/terrain/pending_provenance/` 有 3 TIFF：坡度栅格 EPSG:4326、约 1 km、Float32/LZW；高程同格、Int16，SCA 约 500 m。U 盘未见最终曲率/坡度属性表 | 旧函数可作**重建方法参考**，不能直接复用旧气候/IRI 结果 | TIFF 标签未给出坡度单位或 SRTM/GEE 来源；当前 `compute_road_speed.py:230-239,297-300` 只消费字段、缺失即设零；需确认 NoData/单位、生成全部道路坡度/曲率及 ID 关联、判断投稿运行是否真的使用 |
| Natural Earth 城市点 | 当前和旧代码指定 `ne_10m_populated_places.shp`；已审 U 盘/iCloud 未找到原始点；旧 iCloud `africa_layer.zip/africa_nodes.csv` 有 84＝50 首都+34 大城，包含唯一 `ESH_capital/Bir Lehlou`；ZIP SHA-256 `4de23479d5176429c16bd534ba976976bbea13fd441fe636e062031d9ca1a077`；国家层 801 节点/50 国 | 正式口径按用户确认剔除 WestSahara：可从旧 84 节点**精确筛选 `iso3 != ESH` 得到 83 个历史坐标输入**，无需重新猜城市位置；筛选时保留源 ZIP 哈希及规则。旧 84 节点结果不得直接复用 | 旧 `africa_city_isolation.csv` 确为 84 节点计算，Bir Lehlou 对其他 83 城全部不可达，其余行也把它纳入 OD 分母；旧包无逐 OD Africa 表，不能仅删一行就称 83 节点新结果。原 Natural Earth 下载版本仍未核源，但不阻止利用该历史节点中间表重建 OD 输入 |
| 医疗设施（永久重建输入） | 原 iCloud `中间数据/health_facility_pw_delta_t.gpkg` `quick_check=ok`、POINT EPSG:4326；提取 CSV 与同 SQL 查询逐字节一致，87,118 行/50 国；每点 geometry 与 `lon,lat` 完全一致；50/50 国设施数与旧 `country_accessibility_summary.csv` 相等；GPKG/CSV SHA 及 SQL 见新目录 manifest | 用户确认原始医疗 CSV 修复失败；已将单份 CSV **移动**到 iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/`，作为永久、带血缘说明的**旧设施坐标重建输入**。保留 50 国档案，正式分析显式排除 WestSahara，不复制 50 份 iCloud 文件 | 非原始 OSM 导出，无法恢复 OSM ID、Overpass 查询/抓取日期/原去重规则；12,734 条空名称保留（旧代码只用坐标）；同国内有 95 条重复坐标/类型额外记录，跨国 173 组相同地点/类型/名称重叠，多涉及 WestSahara。不能把 87,118 当泛非唯一设施数 |

## 旧结果可复用等级

| 等级 | 代表文件/内容 | 可做什么 | 不可做什么 |
|---|---|---|---|
| A：重建输入 | 永久设施 CSV；原 GPKG 仍作只读源 | 按 49 国筛选，作为旧研究设施坐标集合的可追溯替代输入；后续可在 run-specific scratch 按国切分给旧代码接口 | 宣称恢复了原始 OSM 抓取时间/ID，或将 GPKG 的 `pw_*` 旧输出当新医疗结果 |
| B：旧口径中间表 | `health_accessibility.zip` 50 国逐节点 `t0/t1/pop`；`result.zip` OD `t0/t1`；旧速度 ZIP；旧 NI/CV 全边分数 | 追溯旧 TGR/覆盖等统计定义、对照校正运行、部分从表出发的旧口径再聚合 | 代替新图/新人口计算；推回固定路径边序列、767 条边的可靠 km 或 MIROC 2085 速度 |
| C：旧声明/敏感性摘要 | 国家汇总、71.7/71.2 恢复、随机均值/标准差、robustness proxy、未来排名摘要 | 对账论文旧数、确定代码旧重复次数（5）及需重新检验的假设 | 从均值/SD 合成逐次随机试验或真实置信区间；把缓存 proxy 称为全量排除人口空间统计 |
| D：不得混合的旧包 | `health_accessibility_future.zip/present`、`_INCOMPLETE`、不明血缘 pickle | 仅隔离、定位来源 | 与旧 `health_accessibility.zip` 基准混算；Kenya 两包样本分别 29,751/54,995 节点、人口 45,736,488.6/146,639.63，显然不是同一分析总体。不要反序列化不明 pickle |

WestSahara 的旧医疗汇总 `n_nodes=137,total_population=137`，与 `compute_health_accessibility.py:610-614` 缺 WorldPop 时每节点 `pop=1` 的回退吻合，**绝非真实人口结果**。旧 `africa_layer` 构图代码枚举 50 道路目录且速度包有 WestSahara 表，所以旧泛非图可能包含其道路作过境；是否实际进入旧 checkpoint 尚无法在不安全读取 pickle 的前提下证实。正式重建应明确“ESH 不作 OD/国别结果”与“ESH 路段是否可通行”是两个不同决策。

## 数据核对后的执行闸门

1. **已放行的仅是文件身份/格式或重建血缘**：FRST RAR 官方 MD5；iCloud CORDEX 30 文件内部一致；U 盘→iCloud WorldPop/GADM 哈希；医疗 GPKG→CSV 逐记录完整导出。旧输出的**计算方法和最终版本仍未放行**。
2. **P0 方法/连接缺口**：道路原始 ID 到速度/图边映射；MGD、IRI 12.0、有效速度/阻断率的物理定义；月降水真实月长、120 月聚合 vs 12 月迭代、未来 10/11 年；坡度/曲率生成链和 SRTM 来源。这些决定是否必须整链重算。不要为了追原数调参。
3. **P0 样本缺口**：正式 49 国/83 非洲城市节点及 WestSahara 道路过境规则；WorldPop 与 GADM 最终人口分母/边界导出。83 个旧坐标可由历史 84 节点表精确剔除 ESH 得到，Natural Earth 原件缺失是血缘限制而非实算输入缺口；旧 84 节点**结果摘要**仍不能无损变成正式 83 节点结果。
4. **审稿必补计算仍待执行**：同 OD 固定路线 vs 重选路；排除人口空间分布和分母；TGR 两定义追源与修正后统计；0.1%/1% 入选边 km；随机铺装逐次重复/不确定性。NI-only/CV 恢复对照先核旧表；未来排序为可行时分析；医疗干预公平结果取决于是否保留相关政策主张。见主 checklist。

World Bank 指标、Idai/Kenya 外部事件观测与新增成本数据不属于上述道路/医疗核心输入的已放行部分；只有保留相应回归、外部案例或真实经济成本主张时才需单独核源。本轮未替审稿人要求臆造投资成本。

本轮只做文件、字段、坐标、哈希、样本口径及旧结果血缘核对与设施输入归档，**未启动新的道路/网络/医疗科学重算**。iCloud 同步目录中能读取并不等于已独立确认服务器端上传完成；未删除 U 盘源、旧 GPKG 或旧结果包。
