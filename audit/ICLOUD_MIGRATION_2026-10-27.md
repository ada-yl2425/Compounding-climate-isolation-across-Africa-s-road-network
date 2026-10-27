# Africa pavement iCloud 迁移记录（2026-10-27）

## 当日新增：WorldPop、GADM 与旧设施点候选恢复

**后续核对与归档更新**：原医疗 CSV 修复失败，用户决定长期采用 GPKG 提取。已将原 `02_derived_checkpoints/recovered_health_facilities_candidate/` **移动而非复制**至 iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/`；其中单份 CSV 哈希不变，并新增 README/manifest。CSV 与 GPKG 指定六字段重导出逐字节一致，87,118 POINT 的几何/经纬度逐一相等、50/50 国旧设施数相符；原 OSM ID/抓取日期无法恢复。用户确认 WestSahara 数据缺失，正式分析排除此地区，50 国重建表仅为完整旧档；详见 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md)。下文旧候选路径仅记载迁移历史，已非当前文件位置。

- 从重新挂载的 U 盘 `WorldPop/` 复制 53 个 `*_ppp_2020_UNadj_constrained.tif` 到 iCloud `01_sources/population/WorldPop_2020_UNadj_constrained_candidate/`。53 个源/目标逐文件 SHA-256 均一致；总源字节数 714,791,286。53 国覆盖研究 50 个道路地区中的 49 个，**缺 WestSahara/ESH**；多 COM/CPV/MUS/STP 四个小文件。栅格头部与论文要求的 2020 constrained UN-adjusted、约 100 m 产品形式吻合，但发布版本、下载记录与逐国人口总量尚未核对，故目录仍标 `candidate`。
- 复制 `GADM边界.zip`（1,466,771,821 字节；SHA-256 `4eb416375d9352654bb55f205cc710db3f0568503011724971be7eb6b4cc861c`）到 `01_sources/boundaries/GADM_v4.1_global_candidate/`；复制已处理的 `africa_gadm41_level2.gpkg`（373,673,984 字节；SHA-256 `a05e4dae93de62ef193a87e5a8c8d1ef841372db9a7412414542f45710e735eb`）到 `02_derived_checkpoints/boundaries/`。两者源/目标哈希一致。ZIP 内是全球 `gadm_410.gpkg`，**没有再复制 U 盘 2.6 GB 未压缩副本**。非洲 L2 工作集有 53 个 ISO、56,680 行，缺 ESH；全球源有 ESH 4 条 L1 边界。旧代码要逐国 L1/L2 SHP，后续需从源按国导出并检查字段/几何，不能把现有 L2 工作集直接宣称为逐国 SHP 的无损替代。
- 从 iCloud `中间数据/health_facility_pw_delta_t.gpkg` 机械导出 `fid,country,name,amenity,lon,lat` 至 `02_derived_checkpoints/recovered_health_facilities_candidate/health_facilities_from_legacy_gpkg.csv`，并放同目录 `README.md` 记录 SHA、查询及限制。87,118 个设施点/50 国与旧医疗汇总逐国设施数吻合；这是可用于和修复中的原始医疗 CSV 比对的**旧输入候选**，不含抓取日期/OSM ID，不替换原始档，也不将其中旧医疗结果升级为新结果。
- 已完成上述本机 iCloud 同步目录副本的复制及哈希检查；`brctl status` 显示新增 GADM ZIP 和部分 WorldPop TIF 仍为 `needs-upload`/`active`，**尚未证实服务器端同步完成**。未删除 U 盘或 iCloud 旧资料；本机可用空间约 18 GiB，不宜继续搬运大型重复档。

目标：`~/Library/Mobile Documents/com~apple~CloudDocs/africa pavement/`。本次是**复制**，U 盘和本地暂存原件未删除；未运行新的科学计算。iCloud Drive 已在本机出现，但上传是异步的。本记录中的“已复制并校验”仅指同步目录中的本地副本，不能等同于服务器端上传完成。

## 证据等级

- **A：官方原始来源身份已核实**。`01_sources/roads/FRST_figshare_29424107_v1/` 内 50 个 `.rar` 共 3,372,489,332 字节，逐个与论文所引 Figshare 记录 `10.6084/m9.figshare.29424107.v1` 的文件名、大小、MD5 一致；U 盘原件与 iCloud 同步目录副本均通过。逐文件清单见 `FRST_FIGSHARE_VERIFICATION.csv`。这证明是官方发布包，不证明论文最终图构建时没有二次过滤或改动。Figshare 记录另有 `read me.xlsx`，U 盘未见，故本次未复制。
- **B：历史派生检查点，可用于追溯/对照，不可当成校正后的正式结果**。下列 ZIP 均通过 ZIP CRC 测试，复制后 SHA-256 与源一致。它们包含有用的道路速度、节点、OD、医疗可达性或审稿稳健性中间表，但来源链与论文口径尚未完全放行。

| iCloud 相对位置 | 内容与用途 | SHA-256 | 限制 |
|---|---|---|---|
| `02_derived_checkpoints/legacy_reference/road_speed_cordex.zip` | 基准道路速度；50 国 CSV，可作为旧口径网络重加权参照 | `2b1f70cbf7d079f04fe306ca683e8db115ef2539a9782fdd1ddccdca2c21589e` | IRI/MGD、时间步长及道路 ID 尚待复核；不是重算后的速度。 |
| `02_derived_checkpoints/legacy_reference/road_speed_future.zip` | 6 个未来情景目录，300 个实 CSV | `2a76ccaacddd7be32f88456ac8c922c1102c19b51d0acb222d8629f436cfcf92` | 缺论文所述 MIROC-MIROC5 RCP4.5 2085；真实年份窗口待证。 |
| `02_derived_checkpoints/legacy_reference/web_components/africa_layer.zip` | 既有泛非城市节点表 | `4de23479d5176429c16bd534ba976976bbea13fd441fe636e062031d9ca1a077` | 节点筛选与论文 83 城市口径待复核。 |
| `02_derived_checkpoints/legacy_reference/web_components/country_layer.zip` | 国别城市节点表 | `bb51f3b4d2cc6ec9c0a93f0523cb8871070fe34117bd436f31289196e06bb157` | Natural Earth 源版本待证。 |
| `02_derived_checkpoints/legacy_reference/web_components/health_accessibility.zip` | 既有国别医疗节点可达性表 | `6f004995cfb8008f4a3bb811ef7d24f9df422392a83a2b42f6301ef974032d1e` | 无原始设施 CSV 时不能重建排除人群；旧权重/口径待核。 |
| `02_derived_checkpoints/legacy_reference/web_components/health_accessibility_future.zip` | 既有未来医疗节点表 | `c15ee5bf6157de6cf40796540fad486e6906a72958d6402f1f0b782409753516` | 未来气候源、时窗与基准模型待核。 |
| `02_derived_checkpoints/legacy_reference/web_components/network_results.zip` | 旧国别 OD 矩阵、buffering decomposition、网络检查点 | `8f2d1930615b515fffa0fa1648ef47179f60f5aef58bb2e3f813f9089746ea08` | 缺完整 edge-score/paving 实验表；pickle 不应当不受信任地反序列化。 |
| `03_legacy_results/result.zip` | 旧图表源表与 GPKG | `60edcd862d5bba6484dab86a462fa7db193b71facfb691ea56ca4e3b85fdb9af` | 含 `_INCOMPLETE`；泛非 OD 摘要写 84 城市，与稿件 83 城市不一致。 |
| `03_legacy_results/robustness_outputs.zip` | 旧稳健性表及输入清单 | `27ff3ddd556943f157f862908c5ad226f4bb8683268229ec7c21b9e0cb50f6f3` | 清单记录的是历史 Google Drive 路径；不能证明当前原始输入仍存在。 |

五个 `web_components/*.zip` 是从 U 盘 `web.zip` 中按原字节解出的内层 ZIP，未复制 3.0 GB 的 `city_layer.zip`；因本机空间紧张，该档暂留 U 盘。`web.zip` 也未整体复制。要复用更细的城市网络检查点时再按需选择，不能误以为整个 `web/` 已完成迁移。

## 未迁移为“已确认正确”的候选

- WorldPop TIF 与 GADM 边界：U 盘有候选，文件名/版本形式接近论文，但尚无足够证据证明是论文最终实际使用的逐国版本；Google Drive 对应目录只有失效软链接。
- `道路数据/` Shapefile：与旧速度表至少 Kenya 样本有对应关系，但稳定道路 ID、坡度/曲率字段及 49/50 国口径存在问题。官方 Figshare RAR 已保存，不把二次处理 Shapefile 直接放行。
- TerraClimate 2020–2025、`merged_climate_pave/`：与论文所述 CORDEX AFR-44 月 `pr/mrso` 组合不一致或未核验，不迁入正式来源区。
- 原始 CORDEX `pr/mrso`、医疗设施 CSV、Natural Earth 原始城市点：当前 USB/可见 Google Drive 未找到，不得以派生表替代。

下一次放行必须核查 source ID、哈希、变量/坐标/时窗、道路 ID 与论文结果链；正式重算另建 run_id 和结果目录。详见 `PROVENANCE_GATE_2026-10-27.md` 与本仓库 `audit/RECALCULATION_CHECKLIST.md`。

## 当日后续清理：Downloads/Road_data

- 用户明确确认 `Downloads/Road_data` 内下载文件是正确版本，并要求停止剩余逐文件核对、清理已迁移下载副本。清理前目录包含 50 个国家子目录、250 个 Shapefile 组成文件；此前已抽查及逐字节比对多国文件（含 Kenya、Congo/CongoRep、CentralAfrican、Morocco、Mozambique、Namibia、Niger、Nigeria、SouthAfrica 等），均与 iCloud 官方 RAR 中相应文件一致。**没有完成 250/250 的逐字节比对**，不能把用户确认写成独立技术验证。
- iCloud 官方 FRST 目录保留 50 个 `.rar`，与上述 Figshare 官方记录的文件名、大小、MD5 一致；清理前 `brctl status` 未显示待上传项目。此状态支持已同步，但不能取代从另一台设备检查云端的独立验证。
- 已删除本机 `/Users/tuibubansurfacepro/Downloads/Road_data`；本机可用空间约从 10 GiB 增至 24 GiB。该本地解压副本没有移到废纸篓，若需恢复可从 iCloud RAR 重新解压。
- iCloud 的 `africa pavement/` 中没有第二套 `Road_data`/解压 Shapefile，也未发现重复的道路 RAR。因此没有删除 iCloud 道路文件；保留官方原包，避免误删唯一来源。

## 当日后续整理：CORDEX 气象输入

用户新置入的 `气象数据raw.zip` 已筛出 30 个 `pr/mrso` 月度 NetCDF，放在 `01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1/`。其中 16 个对应稿件主分析和 SI S8，14 个是现有代码 ±5 年窗口的边界核查所需；变量、单位和时间轴已逐文件检查。完整来源、筛选规则、校验和与口径限制见 `CORDEX_SELECTION_2026-10-27.md`、`CORDEX_SHA256_2026-10-27.csv`。本节取代上文“当前缺原始 CORDEX”的旧时点判断；原 ZIP 在筛选文件上传确认前仍保留，不能把本机已提取等同云端已完成同步。
