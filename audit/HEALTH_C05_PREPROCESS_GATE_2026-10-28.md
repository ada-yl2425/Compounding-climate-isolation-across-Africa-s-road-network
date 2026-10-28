# C05 医疗排除人口：可先行的空间预处理闸门（2026-10-28）

本记录只核输入及设计，不使用旧缺陷图生成正式旅行时间、覆盖率或公平结果。正式研究范围为 49 国，排除缺数据的 WestSahara/ESH。

## 已核对的输入身份与覆盖

| 输入 | iCloud `africa pavement/` 相对位置 | 已见证据 | 仍需核定 |
|---|---|---|---|
| WorldPop 2020 UN-adjusted constrained | `01_sources/population/WorldPop_2020_UNadj_constrained_candidate/` | 53 张 `*_ppp_2020_UNadj_constrained.tif`，总计 714,791,286 bytes；正式 49 ISO 全覆盖，额外 COM/CPV/MUS/STP，无 ESH；旧迁移记录逐文件 SHA 一致，Kenya SHA-256 `bf775d71507bf375f14afb316dbdaa0f13fb3d7bff5f3e3d0139591b2706b8d2` | 官方发布版本、逐国总人口与旧论文分母；源文件名/格式一致不等于确认论文旧运行使用相同字节。 |
| GADM v4.1 全球候选 | `01_sources/boundaries/GADM_v4.1_global_candidate/GADM边界.zip` | 1,466,771,821 bytes，SHA-256 `4eb416375d9352654bb55f205cc710db3f0568503011724971be7eb6b4cc861c`；内含 `gadm_410.gpkg` | 与投稿国界的精确版次和像素跨界归属规则。 |
| 已导出的正式国家行政区 | `02_derived_checkpoints/boundaries/gadm41_admin_49country_f0a701b_gha961ead5_20261027/admin_units/` | 49 国 GPKG；`gadm49_output_manifest.json` 的 `failures=[]`，每国输出 SHA 和面积/对称差 QC 为 PASS。部分国家缺 L2 而使用 L1，不可笼统写成“49 国全部 L2”。 | 用于全国分母时应先 union 同一国家行政单元并与全球 GADM 国家层比较；不能把行政层级差异误当人口排除。 |
| 道路 | `01_sources/roads/FRST_figshare_29424107_v1/` | 50 个 RAR，正式 49 国均有源包；独立 C00 正做 49 国稳定道路 ID/旧速度对齐。 | 修正后的图节点、LCC、物理边及边 ID 必须由 C03 输出，不能直接信旧图。 |
| 永久设施重建输入 | `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/health_facilities_from_legacy_gpkg.csv` | 本轮重新计算 SHA-256 `d2af7770f1b4817ea3da015d62b1e8e445b95954d4e5d99b077c923b1bb98638`，与 manifest 一致；87,118 行/50 国，其中 WestSahara 169 行应排除；manifest 记载逐点几何/经纬度匹配与逐国旧设施数 50/50 一致。 | 原 OSM ID、Overpass 查询及抓取日期无法恢复，需以“重建坐标输入”注明，不宣称原始 OSM 导出。 |

## 可与图修复并行做的内容

1. **冻结像素分母账本**：按 GeoTIFF block/window 流式读取 `pop>0`，保留 NoData/负值/NaN 计数；通过像素中心落入国家 union 判断国界内人口。另记录 TIFF 原始总人口、国界内人口及边界跨越像素人口，避免把裁剪差异解释为路网排除。旧代码直接聚合国家 TIFF 所有正像素，故两种分母都要保存，先比对后选择正式口径。
2. **设施坐标审计**：按国家过滤 87,118 行，检查经纬度合法性、`amenity` 类型、同国重复点和落在 GADM 国界内比例；保留原 `fid`，不静默去重。输出设施级 `facility_input_qc.parquet` 与国家摘要。设施到道路节点的最终 snap 还要等待 C03 节点。
3. **道路几何距离描述**：道路原始几何通过 C00 稳定源行 ID 后，可以计算正人口像素到最近道路**线**的几何距离，作为偏远性描述；这是独立于医疗图的输入层分析，不等同旧代码的“最近 LCC 节点距离”或可达时间。须分片建线段空间索引，局部等距投影/测地校核，不能用统一 `经纬度欧氏距离×111`。可先在小国试运行，正式 49 国要等 C00 源身份闸门。
4. **永久中间表**：`population_pixels/country=ISO3/tile=.../*.parquet` 至少存 `pixel_id,row,col,lon,lat,pop,inside_country`；`distance_to_road/` 单独存 `pixel_id,nearest_source_road_id,road_line_km`。按国 CSV 仅存总数和 QC；大结果不写 49 份 GPKG，也不长期留本地副本。

## 必须等待修正图的内容

- “纳入/排除”必须按**修正后图**的 LCC 节点、同一 25/50/100 km snap 阈值及设施锚点判断。原代码 `compute_health_accessibility.py` 第 266–283、302–390 行对设施和人口都用经纬度欧氏最近节点、`distance_deg×111`；应改为真实 km 距离并逐像素保存最近节点、距离、是否 LCC、原因码。道路**线**距离不能替代最近 LCC **节点**距离。
- 排除原因建议互斥且保留原始布尔标志：`outside_country`, `no_valid_population`, `no_road_node`, `beyond_population_snap`, `node_not_lcc`, `no_facility_anchor`, `unreachable_to_facility`, `included`。先列分母与逐级人数，再计算 88.0%/81.7% 的两种候选分母（国界总人口、可计算纳入人口），不能预设旧稿数字已正确。
- 可达时间、30 min/1/2/4 h 覆盖、PWMTT/Gini/TGR、已纳入与排除组基准可达性，只能在 C03 修正图和 C06 新医疗结果后计算。对不可接网者记录 NA 与原因，不填无限大、0 或虚构时间。

## 小国试跑门槛（建议 Djibouti，之后 Kenya 交叉检查）

1. 只读核 Djibouti 人口 TIFF、GADM 国界、设施 CSV 和道路 RAR 的 SHA/大小；确认国家映射 `Djibouti↔DJI↔dji`、CRS、NoData、人口单位。
2. 单 tile 与全部 Djibouti 逐窗口正人口和须一致；所有像素 `pixel_id` 唯一，输出人口和与输入扫描误差不超过浮点求和容差；国界内+外人口守恒。
3. 距离微测使用赤道、高纬、跨 180° 和 25/50/100 km 阈值附近样本，对 `pyproj.Geod` 或独立测地实现核到 `≤0.1 km`；最近线段需用高密度抽样/精确投影小样核对。至少验证一设施和一人口像素的最近**节点**与最近**线**可不同。
4. 输出每个中间文件 SHA、代码 commit、输入哈希、阈值、人口边界规则及 QC JSON；确认无重复/遗漏后再上远程 49 国数组。试跑不能记为审稿正式结果。

当前本机 `/opt/anaconda3/bin/python` 缺 `rasterio/geopandas/pyproj/shapely`，不应在本机仓促安装并大批量读 iCloud TIFF；建议在 cx3 已装的地理模块环境先跑 Djibouti 微测，再以压缩包/manifest 批量传输、远程块读取。小规模 QC 返回 iCloud `05_manifests/`，大 Parquet 放远程 scratch 并定期打包归档，避免 USB/本地双份。

## Djibouti 输入层试跑结果（已执行，非审稿正式结果）

- cx3 PBS `4490570.pbs-7` 退出码 0，耗时 52 秒；远端合成 TIFF/边界/设施集成测试 `3 passed`（本地纯数学微测 `2 passed`，地理库测试跳过）。
- 输入打包一次传输，归档包 SHA-256 `1640d0a3b9e6aac53b21fd3e801e89e8aca3852bad5d2d6749147b63c99da765`；远端解包后 Djibouti TIFF `5c227de29228f628cfe3bd2777b8cc5a1d11c5eae6a893f103c2560d7383f3fe`、边界 GPKG `2a8acaf4266e0c02630882cfe5ee8f7d755b3b5d2891d110507eec1b8688ca79`、设施 CSV `d2af7770f1b4817ea3da015d62b1e8e445b95954d4e5d99b077c923b1bb98638`。
- 18,980 个有效正人口像素、栅格总人口 `988,002.0047426224`；中心落在 GADM 国界内 18,910 像素／`984,761.3936977386` 人，国界外 70 像素／`3,240.611044883728` 人，像素数和人口两项守恒。此差额是**分母口径差**，并非道路/医疗排除人口。
- 46 个重建设施；境内像素的测地最近设施距离范围 `0.006825987–113.690497508 km`。对全部 18,910 个境内像素 × 46 个设施穷举复核，16 候选加速的最大绝对误差 **0 km**，无 >0.1 km 偏差。
- 结果与执行时脚本原件存 iCloud `05_manifests/c05_djibouti_input_pilot_20261028/`：`DJI_population_facility_distance_pilot.parquet` SHA-256 `d8134d6aae6ea92320fc5b5bedaace73a535e7218c92197127f0f346f349cb4a`，另有两个 QC JSON 和 PBS stdout/stderr。QC 中 `boundary_rule` 字符串误称 *rasterized*；执行算法实际是 Shapely `contains_xy` 的像素中心严格落界，脚本运行原件 SHA `29905560ad67f4f6efae410d926c56d4b2c893c00a69dd484d89fbbb7a2fee1b` 已归档，后续代码已修正文案。该 metadata 瑕疵不改变数值。
- **未通过正式 C05 闸门**：WorldPop 官方版本/旧论文人口分母未核定；道路距离与修正图 LCC 节点分配尚未计算。不得把本试跑设施直线距离解释成医疗旅行时间，也不得把 `984,761` 当作论文覆盖率分母直接使用。
