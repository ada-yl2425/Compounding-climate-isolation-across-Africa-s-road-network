# 论文—代码—U 盘三方数据溯源闸门（2026-10-27）

本表只核对可见文本、代码、文件名/表头/样本元数据；没有做科学重算，也没有从文件名推定原始数据一定正确。`冲突`=已经看到不一致；`待证`=目前不能证明是论文最终所用版本；`可对应`=形式一致但仍需哈希/版本验证。任何 `冲突` 或 `待证` 原始输入不得直接标为正式重算数据。

| 数据/口径 | 稿件或 SI 所述 | 代码实际要求/行为 | U 盘可见证据 | 结论与放行条件 |
|---|---|---|---|---|
| 道路来源与范围 | 主文 Methods: Liu et al. 引用 20；49 国、约 340 万 km，逐段铺装分类 | `RAW/Road_data/{country}/{country}.shp`；脚本列表 50 文件夹；国别 OD 后为 49（SI S1 解释 WestSahara） | `道路数据/` 约 11 GB，约 50 国；Kenya DBF 字段只有 `ID,Start_pt,End_pt,Rd_length,Surface`，无源版本标记 | **待证**：需 Liu 数据版本、原始包、每国源文件哈希、道路总长/数量、49/50 口径与论文汇总逐项核对。该 Shapefile 与派生速度首行几何/长度相符，支持“同一批道路”，但不证明最终版本或来源许可。 |
| 道路稳定 ID | 论文按 road segment 统计与干预 | 速度脚本先按原始行序赋 `country_road_i`；多个图脚本先过滤 `<0.1 km` 再重新编号；基准速度过滤 `<0.05 km` | 速度表有 `Kenya_road_0` 和长度/中心坐标；道路 DBF 不含 `road_id` | **冲突**：必须按几何/原始行号核匹配，重建不随过滤变化的 ID，并量化已有图中错配比例。不能仅因 CSV 能 join 就放行。 |
| 坡度与曲率 | 主文 Methods: SRTM 1 km/GEE 坡度，几何计算曲率，进入 HDM-4 | `compute_road_speed.py` 和 `future_road_speed.py` 在字段缺失时直接填 0；仓库未见提取 SRTM/曲率脚本 | Kenya DBF 仅五字段，无 `slope_deg`、`curvature_deg_km`；U 盘目录未见 SRTM/坡度栅格 | **明确冲突（至少所查 Kenya 文件）**：要么找回真正含坡/曲率的最终道路表及处理记录，要么承认旧计算采用 0 并重做敏感性/改稿；不能继续写“已提取并用于模型”而不验证。其余国需逐国查 DBF schema。 |
| 基准气候模型与时窗 | 主文：CORDEX Africa AFR-44 0.44°，MPI-M-MPI-ESM-LR→SMHI-RCA4，2011–2020 月 `pr/mrso` | `compute_road_speed.py` 查找 `pr/mrso_AFR-44_MPI-M-MPI-ESM-LR_rcp45_r1i1p1_SMHI-RCA4_v1_*`，2011–2020 | USB 无这种 NC；有 TerraClimate `ppt/soil` 2020–2025 与气候-道路合并表 2020–2025 | **冲突/缺失**：TerraClimate 不是此 CORDEX 组合，年份/变量名也不同；`merged_climate_pave` 不能直接替代。需找回 NC、ESGF dataset ID、checksum、time/calendar、units，验证基准时期确实取所述文件。 |
| “CMIP6”措辞 | 主文引言称 high-resolution CMIP6 projections | 代码使用 RCP4.5、MPI-ESM-LR、MIROC5、AFR-44 旧 CORDEX 命名 | USB 未来速度档名同代码命名 | **高度疑似冲突**：CORDEX 官方把 AFR-44/RCP 组合列于 [CORDEX-CMIP5 simulations](https://cordex.org/data-access/cordex-cmip5-data/cordex-cmip5-simulations/)；应追查原 NC global attributes 后修正文案，不能据此称 CMIP6。 |
| 月降水总量 | 主文称 monthly total precipitation，模型降水单位 m/month | 月度 `pr` 通量统一乘 `86400×30`；日度 `pr` 路径逐月求和 | 原 CORDEX NC 缺失，无法核对单位/日历 | **待证且有方法差异**：固定 30 天是近似，不是各月真实日数；对日历类型、闰年及时间界限核验后确定是否需要重算。 |
| 未来气候成员与时窗 | 主文：MPI 与 MIROC，RCP4.5，2041–50/2061–70/2081–90；SI 另加 MPI RCP8.5 2085 | `future_road_speed.py` 的 `period±window` 两端都包括；若 period 2045/2065/2085、window=5，则是 2040–50 等 **11 年**；用文件名无法确定实际运行参数 | `road_speed_future.zip` 仅 5 个 RCP4.5 组合：MPI 三期、MIROC 2045/2065；再有 MPI RCP8.5 2085。没有 MIROC 2085 | **冲突/待证**：至少缺论文要求的 MIROC 2085 速度；未来实际取样时窗需运行命令、日志、输入时间戳及代码版本证明。不能把 `2045` 文件夹自动解释为 2041–2050。 |
| 基准/未来铺装路处理 | 主文默认泛非铺装路为气候中性；SI S5 将 80 km/h 等作为敏感性 | 基准图对未匹配速度边使用未铺装速度中位数、`w1=w0`；未来速度脚本把铺装设为 80→65 km/h（非中性） | 未来速度 ZIP 内 CSV 包含 `Surface`；尚未逐边计数 | **冲突风险**：需判断未来稳定性是否只筛未铺装边、何处使用未来铺装值；把“主模型”与“敏感性”单独标 run_id。 |
| WorldPop | 2020 constrained, UN-adjusted, 100 m | `RAW/Pop_data/*_ppp_2020_UNadj_constrained.tif`，缺失/读取异常时可退化成 `pop=1` | `WorldPop/` 文件命名形式吻合，约 684 MB | **可对应但待证**：核对国家覆盖、TIF 元数据/分辨率、WorldPop 发布版本、栅格总人口与论文分母；正式运行禁止静默 `pop=1`。 |
| 医疗设施 | OSM via Overpass API，医院/诊所/健康中心等；需时间和过滤条件 | `RAW/Health_data/{country}_health.csv`；读取 `lon,lat`；代码提示 `fetch_health_facilities.py` 但本仓库无该脚本 | USB 外层未见医疗设施 CSV；`web.zip` 只有节点/汇总派生表 | **缺失**：须找回最终设施导出、Overpass 查询、提取日期、去重与设施类型映射，否则不可忠实重建医疗图。节点摘要不能恢复设施位置与全部排除样本。 |
| 城市/OD 点 | Natural Earth 1:10m，49 首都+34 非首都巨城；国别节点按 S1 | `RAW/ne_10m_populated_places/ne_10m_populated_places.shp`，`prepare_*_layer.py` | 原始 Natural Earth Shapefile 未见；`web.zip` 内有 `africa_nodes.csv`、`all_city_nodes.csv` | **派生可用、原始待证**：旧节点可固定 OD 样本复核，但重新审计城市来源/版本与 49/83/801 数量须找回原始 NE 文件或原始下载元数据。 |
| GADM | v4.1 国家/二级行政边界 | 多个代码模块从 `RAW/GADM_admin` 或已有边界图层读取 | `gadm_410.gpkg`、`africa_gadm41_level2.gpkg`、`GADM边界.zip` | **待证**：文件名提示 v4.1 但需 GPKG 图层元数据、ISO/行政数、CRS、哈希与论文所用区界版本对齐；勿混用 GADM 4.1 裁剪与其它层。 |
| 旧结果/稳健性 | SI S4 自称部分 health/recovery 是 cached headline + scenario severity screening，非全链路重跑 | `sensitivity/*` 中确有缓存重汇总与近似代理方法；主结果文件散在 `web.zip`/`result.zip` | 包内有 `_INCOMPLETE`，`web.zip` 缺 `02_edge_scores.csv`、`04_paving_experiment.csv`，但有 pickle 和部分汇总；历史 inventory 的云端路径当前不可访问 | **仅作为旧结果对照**：每项先标“正式重跑/缓存代理/不完整”，不得把敏感性表写成完整模型重算。 |

旧 `robustness_outputs.zip` 的 `country_input_inventory.csv` 将 50 国的 `health_csv` 标为 `True`，`raw_climate_rcp_inventory.csv` 也列出许多 CORDEX 相对路径。这只能证明生成清单时另一处工作目录曾有这些文件，**不是**当前 U 盘/本机仍可读取的证据；本轮 U 盘目录和本机桌面范围检索未找到这些原件。后续应按旧清单的相对路径去原项目云端/集群寻找并验证哈希。

## 数据放行顺序

1. **身份**：找到原始来源、版本号/下载日期/许可、完整 SHA-256；文件大小/名字只算线索。
2. **语义**：变量 `pr/mrso`、单位、频率、日历、GCM/RCM/情景/成员、道路字段/CRS、人口/设施定义与论文完全对齐；差异列成决策，不暗中替换。
3. **链路**：抽样逐路段比对原始道路→气候格点→IRI/速度→图边，逐城市/节点比对图→OD/医疗摘要，并核对 49/50 国约定。
4. **结果**：只有上述通过且正式 `run_id` 的产物才进论文数值核对表。若原始 CORDEX、坡/曲率或设施找不回，必须先决定“忠实复现旧口径并纠正文案”还是“另起经过说明的新模型”，不能称二者为同一次重算。
