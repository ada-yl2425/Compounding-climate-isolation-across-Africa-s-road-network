# C01/C02 气候与地形输入闸门（2026-10-28）

范围仅为输入和旧结果血缘核验；没有运行新的道路速度或审稿指标。审稿依据为 Reviewer 1 必需 6 与次要 6、Reviewer 2 次要 3。审稿文本及完整任务映射见 `REVIEWER_RECALCULATION_CHECKLIST.md`。

## 可复核证据

1. `hpc/audit_climate_input_gate.py` 对论文基准、两种 GCM × 三个未来十年窗、SI S8 的 MPI/RCP8.5 共 **16/16 个 `pr/mrso` NetCDF** 核对 SHA-256、成员属性、变量单位、连续 120 月、201×194 格点与 `time_bnds`：全部 PASS。逐文件报告 `climate_input_gate_2026-10-28.json`，报告 SHA-256 `5b9b3e50aeee2cc8df67fae0fffad866ac7ec1720f2d812b250d2fb8b10839af`。源文件位于 iCloud `africa pavement/01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1/`；校验和对的是本次留存清单，并非 ESGF 官方校验和。原下载 dataset ID/版本记录仍缺。
2. `pr` 为 `kg m-2 s-1`，`mrso` 为 `kg m-2`；基准 MPI/RCP4.5 与未来 MPI 为 `proleptic_gregorian`，未来 MIROC/RCP4.5 为 `365_day`。时间界限有 28、30、31 天，MPI 跨闰年另有 29 天。投稿旧代码固定 `30×86400` 秒；当前代码已改按 CF `time_bnds` 或日历月长，相关合成 fixture 16 项通过。故正式重算速度时必须重算月降水及其后续 IRI/速度；旧速度表不能被视为这一新口径的结果。
3. 论文 Methods 指定基准 2011–2020、未来 2041–2050/2061–2070/2081–2090，当前未来速度脚本的默认年份已与三组 120 月一致；旧脚本默认的 `period±5` 或旧调用的 `±4` 并非论文十年窗。旧未来 CSV 的实际运行参数/日志未找到，不可用文件名推断其已满足论文口径。
4. 投稿主文把 MGD 写成 mean gravel depth、SI S2 写 `0.5 m`；公式来源的 [Paterson 原文](https://onlinepubs.trb.org/Onlinepubs/trr/1991/1291vol1/1291-056.pdf) 与 [HDM-4 Part C 手册](https://bmm.doh.go.th/website/download/consultants/%E0%B9%82%E0%B8%84%E0%B8%A3%E0%B8%87%E0%B8%81%E0%B8%B2%E0%B8%A3%E0%B8%9B%E0%B8%A3%E0%B8%B1%E0%B8%9A%E0%B8%9B%E0%B8%A3%E0%B8%B8%E0%B8%87%E0%B9%82%E0%B8%9B%E0%B8%A3%E0%B9%81%E0%B8%81%E0%B8%A3%E0%B8%A1%E0%B8%9A%E0%B8%A3%E0%B8%B4%E0%B8%AB%E0%B8%B2%E0%B8%A3%E0%B8%87%E0%B8%B2%E0%B8%99%E0%B8%9A%E0%B8%B3%E0%B8%A3%E0%B8%B8%E0%B8%87%20%28TPMS%29/%E0%B9%80%E0%B8%AD%E0%B8%81%E0%B8%AA%E0%B8%B2%E0%B8%A3%E0%B8%88%E0%B8%B2%E0%B8%81%E0%B8%9E%E0%B8%B5%E0%B9%88%E0%B8%99%E0%B8%B9%E0%B8%97/0_data/hdm-4/V4/Part_C.pdf) 将 MGD 定义为无量纲材料级配 dust ratio `P075/P425`，不是深度。代码使用统一常数 0.5；这足以要求修正文/SI 单位与定义，但**单凭名称错误不能认定旧数值错误**。FRST 道路源无筛分粒径，因此 0.5 应标为假设，而非路段实测。`max(...,12.0)` 为目标 IRI 下界，不是 SI S2 所称 maximum cap；初始 IRI 6，逐步状态可小于 12。用户已决定保留投稿实现 `Δt=1/12 年`、12 次更新；这不等于证明原经验系数已按年重新标定，须在方法中透明说明。
5. FRST 道路源 50 国 DBF 统一五字段 `ID,Start_pt,End_pt,Rd_length,Surface`，没有 `curvature_deg_km` 或 `slope_deg`。当前 `data_procession/compute_road_speed.py` 的 `load_roads` 在缺字段时直接写零；`future_road_speed.py` 的计算函数也以零回退。论文 Methods 则明言几何曲率与 SRTM/GEE 坡度已进入 HDM 模型，二者冲突。旧仓 `new_conclusion_1` 提交 `bedc5ea55efae1fe85126cf3a415b02506ab6a6e` 的 `data_procession/compute_road_loss.py:129–171` 确有几何转角/公里和 `africa_slope_1km.tif` 质心采样，但属于**另一套**日降水/路损链，不在投稿 `compute_road_speed.py` 的调用链上，不能据此证明已发表速度使用地形字段。
6. 为直接核对旧速度，`hpc/audit_legacy_speed_terrain.py` 用投稿旧式固定 30 天换算及 **零坡度/零曲率**，从 iCloud 基准 NetCDF 重算 Kenya 旧 CSV 的 411 个分布式路段样本。旧 IRI_normal/IRI_extreme 与零地形预测最大差分别 `5.42×10^-6` / `5.79×10^-6` m/km，411/411 对两项均在 `1×10^-5` 内。报告 `kenya_legacy_speed_zero_terrain_2026-10-28.json`。再独立抽取 Benin 105 条，本机最大差 `4.51×10^-6` / `5.25×10^-6` m/km；cx3 隔离 PBS 作业 `4490584.pbs-7` 成功退出后，同 105 条的最大差仅 `3.55×10^-15` / `5.33×10^-15` m/km（机器精度）。远端报告 SHA-256 `9c6bc90e681254d21d90732393f68a82b5c45057861c6465df89c296b9d69441`，本地副本 `benin_legacy_speed_zero_terrain_cx3_2026-10-28.json` 校验一致；本机与 cx3 的微小差异属于数值栈差异，不影响零地形结论。这强烈支持 **这两国的旧速度实际上采用零地形**，但不证明所有国家都如此，也不能替代原运行日志或中间表。此检验故意忠实于**旧** 30 天算法，不能用于新结果。
7. iCloud `01_sources/terrain/pending_provenance/` 有 `africa_slope_1km.tif`、`africa_elevation_1km.tif`、`africa_sca_500m.tif`，其中 slope TIFF 是 EPSG:4326、约 0.008983°（近 1 km）栅格、40,076×20,038 像元、Float32/LZW；栅格外框约 `[-180,180]×[-90,90]`，**不等于全球都有有效坡度**。cx3 `GDAL_PAM_ENABLED=NO gdalinfo -approx_stats` 只读近似扫描给出有效样本占 3.51%、最小 0、最大 21.195、均值 0.937；这些范围与角度坡度相容，但百分坡度也可能落在此范围，**不能据此确认单位**。TIFF tag 没有坡度单位、SRTM 产品 ID、GEE 导出脚本或 NoData 说明；cx3 rasterio 读到 slope `nodata=null`，除 `AREA_OR_POINT=Area` 外没有说明性 tags。用户确认 `Geom_data` 文件夹可用是重要来源线索，但不能据此推定 `slope_deg` 已经过科学验证。当前 `/Volumes/GALACTIC/非洲道路proj/` 未挂载，无法在此轮再次核对 U 盘地形原件；iCloud 候选及其 SHA 已可读（slope `bd2d839c2398dd4dd87980014a7d24028753c8588c0277ad0b7f1b6ae6f88242`）。该 TIFF **可用于抽样/调试重建流程，不可未经来源与单位确认直接用于正式 C02**。曲率无需另下载栅格，可由原道路几何按明确算法重建；坡度需要该 TIFF 的单位/NoData/生成记录，或重新从论文指明的 SRTM/GEE 源提取。

## GO / NO-GO

**用户已选择“补入地形重新建模”。当前结论：正式 C02 全 49 国速度重算 NO-GO，旧零地形速度不得作为新论文结果。** 数据文件本身已经够覆盖论文气候组合，主要阻断是地形单位/来源、逐路段重建和旧运行血缘。不能在“论文已使用坡度和曲率”的表述下，默默按零字段批量运行。

可并行开展**不作为论文新结果**的零地形旧口径对账、单国新代码 smoke test、道路 ID/图边工程核验。用户已选下面第二条；第一条仅保留为旧实现血缘说明：

- **忠实旧数值实现**：把论文 Methods/SI 改为明确旧速度的坡度/曲率未纳入（至少 Kenya 已有强证据），以统一零地形生成新速度；此时仍因真实月长、未来时窗和图权单次通行率而重算受影响下游，并标明 0.5 dust-ratio 与 `1/12` 为假设。需进一步检查其他国家旧速度是否同样零地形。
- **按论文已写方法重建（已选）**：先确定曲率算法、坡度 TIFF 单位/NoData/来源，生成稳定 `road_id` 对应的逐路段 terrain 表（建议 GeoParquet/Parquet；至少含 `road_id,slope_deg,curvature_deg_km,source_hash,algorithm_version`），对抽样路段单测后重算 49 国 IRI/速度及全部下游。若 TIFF 血缘无法证实，需要从论文指明的 SRTM/GEE 原件重新生成。

### 最小可执行地形重建闸门

1. 输入：49 国官方 FRST RAR（含稳定原始行序与几何）、iCloud 坡度 TIFF 及其 SHA、SRTM/GEE 导出证据；如后者找不到，则从主文所写 `USGS/SRTMGL1_003` 重做 slope 1 km 栅格。原始 DEM 有利于独立复算，但若已有可核验的 slope 导出源/算法，不必先复制整个全球 DEM。当前 iCloud elevation TIFF 是候选，但不是带 SRTM 产品元数据的原始 DEM 证明。
2. 冻结算法：曲率参照旧仓 `compute_road_loss.py:129–155`，将线段投影 ESRI:102022，累计相邻有效折线方位角绝对转差（跨 ±180° 折返）除以线段公里数；坡度对经纬质心从坡度栅格采样，明确栅格值是**度**，再按 `tan(deg)×100` 转入模型百分坡度。须定义短于三点的线段、空几何、多部件、落在栅格外/无效值、0–90° 检查及无效值处理，不得静默填零。
3. 先在 Kenya/Benin 做单国属性试算与 QC：原始行号 `road_id` 在筛选前赋值，逐边 `slope_deg`/`curvature_deg_km` 非空与范围校验、约束 0.05 km、几何/长度/ID 与旧表对齐；报告非零比例、分位数和极端值，对同一路段验证手算曲率与坡度采样。产出带版本/源 SHA 的 Parquet 属性表和 JSON 验收。
4. 两国通过后才将同一算法提交 cx3 49 国地形属性数组；最终 `road_id` 一对一 join、49 国无遗漏/重复、空值策略通过。再以这张地形表及 16 个已核 NC 运行 C02 新速度（不是旧速度表改列），先单国新/旧差分 QC，再批量；后续图权只计一次通行率。

若旧导出记录无法恢复，可靠重建源是论文已写的 [Google Earth Engine `USGS/SRTMGL1_003`](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003)：目录明确为 NASA/USGS/JPL SRTM V3、30 m 高程（米），其示例以 `ee.Terrain.slope` 生成坡度；[该函数官方文档](https://developers.google.com/earth-engine/apidocs/ee-terrain-slope) 明确输出**度**。重做时须记录 GEE asset ID、计算/重采样/掩膜及 1 km 导出配置、导出日期、栅格 SHA，而不能仅把旧 TIFF 重命名为 SRTM。NASA 的[数据使用政策](https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy)说明 NASA 主导任务数据在未标限制时按 CC0 开放，仍强烈要求引用；Earth Engine 平台使用条款与数据版权应分别遵守。此处是**待执行的可靠来源方案**，不是声称已下载或已生成新坡度。

两个分支都**不能**仅从旧速度 CSV 改写出新 IRI，因为旧表没有每路段的原始月 `pr/mrso` 序列、坡度/曲率和新时间换算所需信息。主审稿网络/医疗指标可先做代码、样本及单国试运行，但正式数字需等待 C02 和图权版本冻结。
