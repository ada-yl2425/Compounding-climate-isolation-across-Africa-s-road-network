# Africa pavement 数据归档与可用性核查（2026-10-27）

本文件是只读盘点和归档方案，不代表任何模型结果已重算。U 盘原件保持不动；旧结果仅作为对照，不作为修正后模型的权威结果。`已见`表示确认文件存在、并非内容或科学口径已通过验证。

## 存储现状与去向

- U 盘只读源：`/Volumes/GALACTIC/非洲道路proj/`，约 132 GB。不得作为后续计算的工作目录或输出目录。
- 本机磁盘仅约 14 GiB 可用。不能无筛选地复制 U 盘全部内容，尤其不能复制约 102 GB 的 `merged_climate_pave`。
- iCloud Drive 已于 2026-10-27 在本机出现：`~/Library/Mobile Documents/com~apple~CloudDocs/africa pavement/`。已复制的批次、校验值与待上传状态见 [ICLOUD_MIGRATION_2026-10-27.md](ICLOUD_MIGRATION_2026-10-27.md)。同步目录中的文件还需确认服务器上传完成；本机仅余约 6 GiB，暂不搬运其它大档。
- 旧稳健性清单记录的 Google Drive `.../我的云端硬盘/africa_pavement` 是历史路径；当前实际挂载目录名为 `我的雲端硬碟`，且其中未见 `africa_pavement`。历史清单中的 `exists=True` 不能视为当前存在。
- 本机暂存区：`~/Desktop/africa-pavement-local-staging/`，仅用于小体量压缩档的分类备份、清单和远程打包准备；不是 iCloud。计算工作集必须在本机高速盘或远程 RDS/scratch 解压后读写，不直接在云同步文件夹上随机读取。

已在上述本地暂存区按类别复制 `road_speed_cordex.zip`、`result.zip`、`robustness_outputs.zip`；源/副本 SHA-256 分别完全一致：`2b1f70cbf7d079f04fe306ca683e8db115ef2539a9782fdd1ddccdca2c21589e`、`60edcd862d5bba6484dab86a462fa7db193b71facfb691ea56ca4e3b85fdb9af`、`27ff3ddd556943f157f862908c5ad226f4bb8683268229ec7c21b9e0cb50f6f3`。其余大档暂未复制；这只是安全备份/分类，不代表内容已被论文溯源放行。

## 归档分类及当前状态

| 类别 | U 盘位置/规模 | 可用性判断 | 应归档位置与处理 |
|---|---|---|---|
| 01 原始道路 | `道路数据/`，约 11 GB；国别 Shapefile | 已见；需审查字段、CRS、国别数、重复边、稳定 `road_id`；`CentralAfrian` 与代码 `CentralAfrican` 不一致 | `01_sources/roads/`；保留原件，另制规范化 GeoParquet/GPKG，不原地改名 |
| 01 原始路面压缩包 | `非洲50个国家和地区的道路路面类型数据集/`，约 3.1 GB，RAR | 已见；可能是道路数据更早版本，先比对来源/版本/哈希 | `01_sources/road_surface_original/`；不要与前一项当作独立观测相加 |
| 01 人口栅格 | `WorldPop/`，约 684 MB，2020 年 TIF | 已见；核对 50 国覆盖、栅格人口单位与缺失值 | `01_sources/population/` |
| 01 行政边界 | `GADM边界.zip` 约 1.4 GB；`gadm_410.gpkg` 约 2.6 GB；`africa_gadm41_level2.gpkg` 356 MB | 已见；可能是不同版本/裁剪层，核对版本、层级与 CRS | `01_sources/boundaries/`；标注哪个用于正式分析 |
| 01 经济数据 | `world_bank_gdp/`，704 KB | 已见；不能直接等同代码所需 `RAW/worldbank_indicators.csv`，需核对字段/年份 | `01_sources/socioeconomic/` |
| 02 原始气候 | `TerraClimate_Africa_Data/`，约 4.3 GB，2020–2025 NC | 已见；**不能直接替代**代码要求的 CORDEX `pr/mrso` 2011–2020 和未来各窗口 | `01_sources/terraclimate/`；单列数据源及用途 |
| 02 气候-道路大表 | `merged_climate_pave/`，约 102 GB，四套方法子目录 | 已见；是派生表，尚未验证字段、时窗和道路 ID，不宜批量搬运 | `02_intermediate/climate_road_joined/`；先样本/元数据核对，只转移可复算所需版本 |
| 02 基准道路速度 | `road_speed_cordex.zip`，311 MB，约 50 国 CSV | 已见；含 `road_id, Surface, length_km, IRI, passable_rate, V, p_block`；**旧口径产物**，可用于对照和有条件的网络重加权 | `02_intermediate/road_speed/baseline/`；保留原压缩包及哈希 |
| 02 未来道路速度 | `road_speed_future.zip`，1.7 GB，6 个场景目录 × 约 50 国 | 已见；场景覆盖不等于完整气候原始输入覆盖 | `02_intermediate/road_speed/future/` |
| 03 网络/医疗中间结果 | `web.zip`，3.7 GB 外层 ZIP，内含 6 个 ZIP | 已见 `node_accessibility_*.csv`、旧图层结果、部分 checkpoint 与 `experiment_state.pkl`；嵌套 `network_results.zip` **未见** `02_edge_scores.csv` 和 `04_paving_experiment.csv`，不能单凭这份包恢复所有实验 | `03_legacy_results/web/`；原包保存，按需解压，旧 pickle 只在可信同环境诊断读取 |
| 03 汇总结果 | `result.zip`，269 MB | 已见 Fig 结果表与 GPKG；存在 `_INCOMPLETE` 文件，不能把它们当正式完成版 | `03_legacy_results/result/` |
| 03 稳健性结果 | `robustness_outputs.zip`，1.4 MB | 已见若干清单、敏感性表、旧路径信息；有旧文件 `exists=True` 但现路径不存在 | `03_legacy_results/robustness/` |

## 关键缺失/待找回

1. USB 根目录没有发现代码所需 `RAW/Health_data/{country}_health.csv`；若别处也没有，医疗设施层、完整医疗重算、固定路径分解均不能从现有摘要表独立恢复。先查原始设施提取流程、许可和版本。
2. USB 未见原始 CORDEX `pr/mrso` 基准/未来 NetCDF；`road_speed_*.csv` 是派生结果。若要修改 HDM-4、月度机制或气候暴露定义，必须找回或重新获取对应原始气候时间序列，并锁定原试验组合、单位与时窗。
3. USB 未见 `RAW/ne_10m_populated_places` 原始城市点；`web/africa_layer.zip` 可提供既有城市节点表，但如需重建样本/纳入规则，仍需原始来源。
4. 完整 `02_edge_scores.csv`、`04_paving_experiment.csv` 在 `web.zip` 内的 `network_results.zip` 中未检出；`result.zip` 有精简/派生版本，未含可靠道路长度。须检索其它保留位置或从校正网络重算。
5. `result.zip`/`robustness_outputs.zip` 包含 `_INCOMPLETE` 与历史清单，不能因文件名存在就标“完成”。

论文、代码与 USB 的逐项一致性结论见 [PROVENANCE_GATE.md](PROVENANCE_GATE.md)。其中已确认的冲突包括 TerraClimate 与 CORDEX 的数据源/时窗不同，Kenya 道路 DBF 不含主文声称已用的坡度/曲率字段，未来速度包缺 MIROC-MIROC5 2085，及道路 ID 在过滤前后生成的时点不同。

## 整理规则

归档时按 `01_sources/`、`02_intermediate/`、`03_legacy_results/`、`04_validated_results/<run_id>/`、`05_manifests/` 分类。每个原档保留文件名、大小、SHA-256、来源、采集日期、许可、CRS、时间范围、版本及 `source → derived` 关系；不得覆盖原始档。大表采用分国别/场景分区 Parquet 或 GeoParquet，压缩传输包只用作运输，不充当可查询主数据格式。每个正式重算独立 `run_id`，结果表不得与旧 `web/` 或 `result/` 混存。
