# 审稿重算输入缺口复核（2026-10-27）

**最终当日更新**：完整数据身份/格式与旧结果可复用分级以 [DATA_VALIDATION_2026-10-27.md](DATA_VALIDATION_2026-10-27.md) 为准。原医疗 CSV 修复失败，用户已采用 iCloud `01_sources/health_facilities/legacy_gpkg_reconstruction_v1/` 的 GPKG 提取 CSV 作永久**重建设施坐标输入**；正式分析排除用户确认缺数据的 WestSahara。旧 84 个城市节点表可按 `iso3 != ESH` 精确取得 83 个历史坐标输入，Natural Earth 原件未找到仍是血缘缺口；旧 84 节点结果不能只删 ESH 行。30 个 CORDEX NC 内部一致，但月长、120 月聚合/12 次同值迭代、未来 10/11 年口径与坡度/曲率链尚未审定。下文先前“医疗原件需找回”“U 盘未挂载”等描述是当时快照，不代表当前阻断状态。

## 新增输入状态更新（U 盘重连及旧结果核查后）

下文旧时点的“U 盘未挂载/WorldPop、边界未在 iCloud”已由 [ICLOUD_MIGRATION_2026-10-27.md](ICLOUD_MIGRATION_2026-10-27.md) 的新增迁移记录取代。WorldPop 53 个 TIF、全球 GADM ZIP 和非洲 L2 工作集现位于 iCloud 同步目录、源/副本 SHA 一致；仍为**候选**，尚缺原下载版本、人口总量、逐国边界导出及 ESH/WestSahara 缺失处理。Natural Earth 原始 populated places 在本次 U 盘定向检索未找到；旧 `africa_nodes.csv` 有 84 节点（50 首都＋34 megacities），不是稿件所称 83，需澄清是否/何时剔除 WestSahara。旧仓已有曲率和坡度生成函数，但与现稿 CORDEX 速度脚本不是同一计算链，须审计后只复用几何提取思路，不可声称旧主结果已用该函数。

另从旧医疗 GPKG 恢复了含 87,118 行坐标/类别的候选表；其逐国行数与旧医疗汇总吻合。该表不含 Overpass 抓取日期、OSM ID 或原始去重规则，不能替代正在修复的权威原件。旧医疗节点和未来医疗节点存在版本冲突，不可混用；旧逐节点固定路径分解仍未找到。

## 当日再次核查：除医疗设施之外

对 iCloud 同步目录作只读核查：`01_sources/roads/FRST_figshare_29424107_v1/` 有 50 个 RAR；`01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1/` 有 30 个 NC；`01_sources/terrain/pending_provenance/` 有 3 个 TIFF。**在同步目录可见不等于再次验证云端上传完成或科学口径已放行**。`01_sources/` 当前没有 `population/`、`boundaries/`、`cities/` 类目录。U 盘 `/Volumes/GALACTIC/非洲道路proj/` 当前未挂载，无法复核此前所见的 WorldPop/GADM 候选。桌面与 Downloads 的定向文件名检索亦未找到这些原件。

Google Drive 挂载的 `africa_energy/raw_data/worldpop/` 和 `gadm/` 有文件名/国别目录，但抽查 Kenya TIF 与 GADM 路径是指向已不存在的 `我的云端硬盘/africa_pavement/RAW/...` 的**失效软链接**，不能计作可读取的数据。

因此，**非医疗 P0** 是：WorldPop 2020 constrained UN-adjusted 逐国 TIF 的实际文件与版本/人口核验；道路坡度/曲率的最终逐边属性或可复建处理链（坡度栅格候选已在，未证明旧计算使用）。**非医疗 P1** 是：Natural Earth 1:10m populated places 原件/节点选择记录，以及 GADM v4.1 边界实际文件/图层核验。旧运行命令、参数、日志、稳定道路 ID 映射及 CORDEX 下载 dataset ID/官方校验属于**溯源证据缺口**，不是让用户另找一个气候模型。World Bank 指标和外部灾害观测仅在保留对应回归/验证分析时需要。

范围：只核验当前可见的 iCloud 归档、先前 U 盘/Google Drive 审计记录、稿件/SI 与代码；没有执行新的道路、路网、医疗或干预计算。`未在 iCloud` 不等于源数据不存在，尤其 U 盘此时未挂载。证据等级遵循 `PROVENANCE_GATE.md`。

## 已到位，但仍有口径闸门

| 输入 | 当前可用位置 | 证据和剩余闸门 |
|---|---|---|
| 道路原始几何及铺装属性 | iCloud `01_sources/roads/FRST_figshare_29424107_v1/`，50 个官方 RAR | 文件名、大小、MD5 与 Figshare `10.6084/m9.figshare.29424107.v1` 一致。仍需确认论文 49 国/代码 50 目录的取舍、过滤前后稳定道路 ID、几何/路面字段。 |
| CORDEX `pr/mrso` 月度原件 | iCloud `01_sources/climate/CORDEX_AFR44_SMHI-RCA4_v1/`，30 个 NC | 文件名、NetCDF 变量、单位、模型/情景全局属性和各 120 个月已核验；16 个对应稿件主分析与 SI S8，14 个暂供代码 11 年窗口审计。仍需原下载页 dataset ID/官方校验和；需解决代码 `period±5` 包含 11 年、稿件只写 10 年，以及 `pr×86400×30` 固定月长。不能因文件到位即放行旧速度结果。 |
| 地形栅格 | iCloud `01_sources/terrain/pending_provenance/`，坡度/高程/SCA TIFF | 用户确认 `Geom_data` 正确，复制后 SHA 对应；但现有原始道路 DBF 至少 Kenya 无 `slope_deg`、`curvature_deg_km`，且仓库缺坡度/曲率写回脚本。须找回最终逐路段属性表或明确重新提取、重算并改稿。 |
| 旧派生检查点 | iCloud `02_derived_checkpoints/legacy_reference/`、`03_legacy_results/` | 可追溯旧口径、比对输出；不是纠正后的正式输入。既有未来速度缺 MIROC-MIROC5 RCP4.5 2085；现在有相应原始 NC，可在方法锁定后补跑。 |

## 仍未达到正式重算输入条件

| 优先级 | 数据或证据 | 当前状态 | 阻断的任务 / 下一步 |
|---|---|---|---|
| P0 | 医疗设施逐点 CSV 与 Overpass 查询、抓取日期、设施类型/去重规则 | 当前 iCloud 未见；先前 U 盘和可见 Drive 也未找到原件。旧节点汇总不能逆推出设施全集。 | 医疗纳入/排除人口、旅行时间、公平、干预医疗效果（C05–C09/C14）；找回原导出或按冻结查询重新抓取并说明版本差异。 |
| P0 | WorldPop 2020 constrained UN-adjusted 100 m 逐国 TIF、发布版本/人口总量核对 | 先前 U 盘有文件名相符的候选，**未在 iCloud 放行**；U 盘目前未挂载，未能做最终哈希/国家覆盖审计。 | 人口加权网络/医疗结果和排除人口空间分析；先从候选核验并迁入，禁止代码静默退化到 `pop=1`。 |
| P0 | 逐路段坡度与曲率的生成链或论文最终道路属性 | 仅坡度栅格候选可见；至少 Kenya 原始 DBF 缺两字段，现有速度代码缺字段时写零。 | HDM-4 模型语义与准确重算（C01–C02）；确认历史实际是否用过这两项，或重建、量化差异、修正文案。 |
| P1 | Natural Earth 1:10m populated places 原始 Shapefile、版本/83 泛非节点选择规则 | 旧节点派生表在 iCloud；原始 NE 数据当前未见。 | 城市 OD 来源及 49 首都+34 其他城市、801 国别节点等复核；可先固定旧节点做局部诊断，正式来源审计需原件。 |
| P1 | GADM v4.1 国家/二级边界与具体图层校验 | 先前 U 盘有 GPKG/ZIP 候选，当前 iCloud 未放行；版本、ISO、图层和 CRS 未核实。 | 人口分母、国别/次国家汇总及地图边界；核验候选后迁入。 |
| P1 | 原始运行命令、日志、参数和旧路段 ID 映射 | 当前 iCloud 未见完整可追溯记录；旧缓存/结果表只有部分链路。 | 判断历史速度究竟取了 10 年或 11 年、坡曲率是否置零、`p_block` 是否重复计入；无日志时须明确“重建新口径”，不能宣称忠实复现旧结果。 |
| 条件 | 逐格设施密度/GDP 源、外部灾害观测、额外 RCP/模型 | 候选和旧结果分散；非所有主分析的启动条件。 | 仅在保留相应回归、外部验证或扩展气候不确定性结论时补齐；不能把 NCC/全部 RCP2.6/8.5 误列为当前主分析必需。 |

## 当前放行结论

- **可以做**：文件/代码/论文口径核对、30 个气象 NC 的格式/元数据 QC、旧结果表的来源追踪、道路 ID 与属性的只读审计；无需立即跑新科学结果。
- **暂不能做正式全链路重算**：医疗设施和已核实 WorldPop 尚缺；坡度/曲率实际使用与气候时窗冲突尚未决议；城市/边界版本和道路稳定 ID 未锁定。
- **优先顺序**：先锁定气候时窗与 HDM-4 物理定义，同时找回设施导出、核验并迁入 WorldPop/边界/城市点，最后建立固定 `run_id` 的正式图、医疗和干预计算。现有 checklist 见 `RECALCULATION_CHECKLIST.md`。
