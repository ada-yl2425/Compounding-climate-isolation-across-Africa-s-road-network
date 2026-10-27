# Reviewer 重算：依赖、并行与 cx3 放行计划

状态：2026-10-27。此文件是执行计划，**不是已完成的科学重算**。正式国别结果为 49 国、非洲城市 OD 输入为 83 节点；WestSahara 无正式结果。是否允许其道路作为跨境过境边仍须在 G0 冻结。审稿条目以 [REVIEWER_RECALCULATION_CHECKLIST.md](REVIEWER_RECALCULATION_CHECKLIST.md) 01–11 为准；技术步骤以 [RECALCULATION_CHECKLIST.md](RECALCULATION_CHECKLIST.md) C00–C16 为准。

## 依赖图与可并行作业

| 阶段 | 必须先生成/决定的产物 | 可并行工作 | 卡点 |
|---|---|---|---|
| G0 规格冻结 | `model_spec.yaml`：MGD/IRI/月长/时窗/通行率；`analysis_population_registry.csv`：49 国、83 城、OD、ESH 道路规则；输入身份、哈希、指标词典 | 道路 ID 审计；气候/HDM 审计；地形来源审计；WorldPop/GADM/设施血缘审计；旧 TGR/恢复率数字追源 | 不明确物理定义、版本和分析样本时，**不得**投批量作业 |
| G1 共享前处理 | `canonical_roads`（稳定物理路段 ID、长度、几何及图边 crosswalk）；由道路几何重建曲率、验证坡度单位并抽样；`road_cell_index`（道路→CORDEX 格点）；83 城 OD/权重注册表；人口像素与设施 snap 注册表、排除原因；一致的图边权重规范 | 地形/格点/城市/人口-设施锚定可分工并行，但必须汇合到同一 ID、CRS 与版本 | 源→路段→图边一对一/多对一关系可追溯；质量与样本守恒通过 |
| G2 路段气候与速度 | G0/G1 的模型及道路-格点映射 | 若发现实现错误：基准及未来可按国×模型×时段并行；人口/设施空间预分配可同时完成 | 单路段手算、月份/日历、IRI 边界、速度/通行率单位测试通过；一国一情景试跑通过 |
| G3 统一图与基础旅行时间 | 放行的路段速度（或有证据证明可沿用旧版）、统一图权重/ID | 国别图可按国并行；泛非图单独高内存作业；冻结图后，城市 OD 固定路/重选路、医疗、NI/CV 可作为三个工作流并行 | 图边数量、长度、速度匹配、平行边、连通、OD 掩码与正常/极端单调不变量通过 |
| G4 审稿专项 | G3 及各自专项前置 | 城市路线分解独立；医疗排除/覆盖与多源最短路独立；NI/CV 排序独立。TGR 等医疗节点表；0.1%/1% km 等入选边清单；随机试验等图+排序；未来排名等未来速度+基准 NI | 每专项逐国/逐情景清单、分母、公式、失败/断连数、输出哈希验收 |
| G5 条件分析及全文对账 | G4 汇总、保留的论断列表 | 敏感性按模型/样本独立；医疗干预仅在保留政策主张时做；全稿数字核对本地执行 | 新旧结果不混用；11 项 checklist 分别附证据并填最终验证结果 |

现有 `tests/test_basic.py` 只是占位测试，不构成 G1–G4 放行。需要覆盖：筛选前后道路 ID 与 0.05/0.1 km 阈值、坡度/曲率单位、CORDEX 真实月份长度与 10 年/11 年窗、IRI 12 上下限、通行率不得双重惩罚、平行边物理 ID、`t_reroute <= t_fixed`（同 OD 且有限值时）、人口分母守恒和 `pop=1` 回退禁用、49/83 样本、入选边长度、固定随机种子及图权重恢复。先使用人工可手算的微型 fixture，再做一个国家及极小泛非 OD 的端到端 pilot，估算峰值内存/运行时间；通过才申请完整数组任务。

## Git 分支与结果隔离

- 集成基底：`recalc/00-foundation`。保留既有审计文件，完成 G0/G1 的规格、映射、测试和远程 preflight；不得覆盖旧结果。
- G0/G1 合并并通过后，按工作流从该提交派生：`recalc/10-climate-speed`、`recalc/20-network-route`、`recalc/30-health-equity`、`recalc/40-bottleneck-paving`、`recalc/50-future-sensitivity`、`recalc/90-claim-audit`。有依赖的分支只能在其上游合并后启动正式结果；可先并行写无依赖代码/测试。不要用多分支同时写同一个共享文件。
- 数据、运行日志和大结果不进 Git。每次运行使用不可复用的 `run_id`，保存 Git commit、输入 SHA-256、环境、配置、任务 ID、输出清单；旧包只读。远程和 iCloud `04_validated_results/<run_id>/` 中的 `PASS` 产物方可供下游使用。

## cx3 运行与传输

参照 `africa-energy/validation/hpc/result1/` 与 `result2/`：cx3 使用 PBS Pro `qsub -J` 数组和 `afterok` 汇总，不是 Slurm。先由用户在交互终端输入 `ssh cx3` 及密码。远程环境预检只读确认登录主机、`qsub`、Python/容器、RDS/scratch 可用容量、配额与软件许可；尚未确认前不假定路径、核数或内存。

首批只传本阶段必需的**少数批次**：50 个官方道路 RAR（ESH 过境规则待定）、30 个 CORDEX NC、必要的 WorldPop TIFF、Africa L2 GPKG、3 个地形 TIFF、医疗重建 CSV、历史城市节点 ZIP及 manifest；不复制整个 iCloud，不上传旧结果包或重复气候 ZIP。道路 RAR、NC、压缩 TIFF 已是压缩容器，避免在本机产生第二份 2 GB 包（本机剩余空间很少）。可用批量 `rsync -a --partial`/`tar` 流，远端逐文件 SHA-256 验证；本机 openrsync 不支持 `--append-verify`，不可照搬。远端高速盘解包和计算，worker 写分片 Parquet；finalizer 核分片数量、schema、CRS、行数、国家/情景范围、缺失和物理不变量，然后仅打包必要结果及摘要回传。Google Drive 若使用 rclone，须设置本项目独立路径并用 `copy`/`check`，不能写入 `africa_energy` 数据区。

## 每个卡点必须留下的证据

1. `input_manifest.json`：源路径、SHA-256、大小、格式、schema/CRS/单位、国家/情景/时间范围、许可与数据血缘。
2. `run_manifest.json`：`run_id`、Git commit、环境、`model_spec.yaml`、随机种子、PBS job ID、输入 manifest 哈希和预计输出分片。
3. `qc.json`：单元测试、单国 pilot 与正式作业逐项 PASS/FAIL；失败清单、NaN/断连/排除数和阈值、手工 spot-check 证据。
4. `output_manifest.json`：每个 Parquet/GeoParquet/CSV 的路径、SHA-256、schema、行数、样本量、公式版本及上游 run ID。需要 GIS 互操作才另导出 GPKG。
5. `REVIEWER_RECALCULATION_CHECKLIST.md`：只有在上述证据和科学数值核对完成后才填“验证结果”和最终数据地址；文件存在本身不代表结果通过。

**当前状态**：只完成静态输入/代码审计和此运行计划；G0 方法决策、G1 共享中间层、科学单元测试及远程 preflight/批量作业均未放行。新增明确 P0：投稿公式原始研究的 `T` 单位为天，当前 `1/12` 无系数换算；MGD 是无量纲 dust ratio 而非 0.5 m 深度，见 [MODEL_GATE_FINDINGS_2026-10-27.md](MODEL_GATE_FINDINGS_2026-10-27.md)。

2026-10-27 本机网络预检：`ssh cx3` 在 SSH 密钥交换阶段即被关闭，未到密码提示；本机 `login.cx3.hpc.ic.ac.uk` 经当前隧道 DNS 解析到 `100.64.1.3`，Imperial Cisco 客户端未连接。已打开交互终端供用户自行输入命令/密码，但须先恢复可用网络／学校 Unified Access；不得猜测备用主机或把密码写入仓库。`python -m pytest -q` 旧套件仅 1 个占位测试通过；新增文件清单哈希验证单测另行记录，**不能**当作科学模型放行。

### 2026-10-27 cx3 工程预检续记（取代上段的“未连接”状态）

用户已在自己的终端建立复用 SSH 会话；自动化只使用本机临时 ControlMaster socket，**没有收集或保存密码**。远端是 `login-bi.cx3.hpc.ic.ac.uk`，账号 `yl2425`。PBS Pro `/opt/pbs/bin/qsub` 可用；非交互命令须先 `bash -lc` 加载环境模块。已确认 `geopandas/0.14.2-foss-2023a`、`xarray/2023.9.0-gfbf-2023a`、`python-igraph/0.11.4-foss-2023a`、`Arrow/16.1.0-gfbf-2023b` 和 Python 3.11 组合；pilot venv 补装 `rasterio==1.3.10`，NetCDF 后端单独检查。远端有 `tools/prod` 下的 `p7zip/17.04-GCCcore-12.3.0`，Kenya RAR 能列出 `.shp/.dbf/.shx/.prj/.cpg`；这只是档案可读性，不是路段口径验证。

工程 pilot 隔离根目录：`/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/pilot-20261027-e3bd600/`。初次代码按 Git 提交 `e3bd600` 的 archive 部署；工程脚本提交后再由 `7cb0fb3` 和 `bbd2866` 的 archive 更新。**该试验目录跨提交使用，只适合工程输入探查；正式科学运行须新建不可复用 run_id 并冻结单一提交。**首批 Kenya **8 个**输入文件共 **398,876,426 B** 从 iCloud 以一份 `--files-from` 清单批量 `rsync` 至 `incoming/`，本地和远端 `hpc.verify_manifest` 均报 `PASS`，见 [kenya_input_manifest_2026-10-27.json](kenya_input_manifest_2026-10-27.json)。远端仓库测试 `8 passed`，只验证文件清单工具等工程行为，不覆盖 HDM/图/医疗模型。

PBS 工程作业 `4479838.pbs-7`（2 核、8 GB）已在 `cx3-3-22` 完成，`Exit_status=0`、峰值约 229 MB；stdout 显示哈希 `PASS`、`8 passed`、`ENGINEERING_INPUT_PILOT_PASS`。结构元数据位于 `results/kenya_input_metadata_qc.json`（SHA-256 `fcf59297b570f2f36401aebc6b9eeb4137bf59b871a4b5acae8400923d99b1f4`），状态 `PASS`：MPI-M-MPI-ESM-LR/RCP4.5 的 `pr` 和 `mrso` 均为 2011-01～2020-12 的 120 月、201×194 格点；`pr` 单位 `kg m-2 s-1`、`mrso` 单位 `kg m-2`，日历 `proleptic_gregorian`。设施重建表共 87,118 行，其中 Kenya 2,520 行，坐标语法无效 0 行。WorldPop Kenya 是 EPSG:4326；`africa_slope_1km.tif` 与 `africa_elevation_1km.tif` 虽可读取、也是 EPSG:4326，实际栅格范围约为 **全球** `[-180,180]×[-90,90]`，元数据未声明坡度单位、来源仍为 `pending_provenance`，不能据此作为已验证的模型坡度。

道路档案 schema 工程作业 `4479850.pbs-7` 亦在 `cx3-3-22` 完成，`Exit_status=0`；`results/kenya_road_schema_qc.json`（SHA-256 `8a708ddf30d9171f4b2f2aaac19103e4bd78cb8309ba48bc9cecc8142c54997f`）确认 RAR 内五件 shapefile 完整、EPSG:3857、504,366 条 LineString、属性仅 `ID,Rd_length,Surface,Start_pt,End_pt`。原始包没有 `slope_deg`/`curvature_deg_km`；若速度代码以该包直接读取，则触发补零路径。道路 schema `PASS` 只表示档案可读，不表示科学字段满足 G0。

进一步抽 `Kenya_road_{0,8,12,16}`，按投稿投影算法从 RAR 几何重建的长度/中心点与 iCloud 旧 CORDEX 速度 CSV 四行精确匹配；报告 `results/kenya_road_alignment_samples.json`，SHA-256 `2eadeee70a1e188d2d150337f917d30a8fb10ea4c993b38115ffcc1678707401`。因此该旧表可用于追踪此道路源的 ID 规则，但**不能**作为新模型速度或坡度单位已经正确的证明。

**没有提交 PBS 科学作业或产出正式审稿数值**；G0/G1 未放行。下一卡点是道路字段/稳定 ID、地形来源和单位、HDM 模型科学规格，再做人工微型 fixture 和单国正式算法试跑；失败时不自动放行批量数组。

### 2026-10-27 后续工程进度

用户明确选定投稿实现的 IRI 月度步长 `1/12` 年、12 次迭代；这不自动校准原经验式的时间单位。降水通量的固定 30 天换算已改为 CF `time_bnds`／日历月长，cx3 环境相关单测通过。独立物理路段图模块已在微型 fixture 保留筛选前 ID 与平行道路；旧结果管线尚未接入。图审计另确认五条旧路径会过滤后重编道路 ID、将通行率再次除入图权，且简单图会吞掉平行边；这三项均为 G0/G1 正式重算卡点。

GADM 全球候选原包 `GADM边界.zip`（1,466,771,821 B）已按单文件压缩容器直传 cx3 共享输入区，不在本地解压或复制到 U 盘；[gadm_source_manifest_2026-10-27.json](gadm_source_manifest_2026-10-27.json) 记录本地 SHA-256。原包 Kenya 提取 PBS 工程作业 `4480013.pbs-7` 已在计算节点完成，`Exit_status=0`，峰值内存约 376 MB、运行 2:19；远端原包 SHA-256 验证 `PASS`。原始全球 GPKG 的 Kenya 1,442 个最细记录聚合为 300 个 L2 单元，EPSG:4326，源/目标对称差 0 km²，几何有效且无显著内部重叠。报告位于 `results/gadm41_KEN_2_pilot_qc.json`；试提取 GPKG SHA-256 为 `211d3230558beeaf868a7261b7d51d764c32902bc258bbc06ec5f654d61f34f6`。解压后的 2.6 GB 全球 GPKG 已移动到远端 `shared_inputs/gadm_v4.1_global_candidate/gadm_410.gpkg`，原试验路径留符号链接，避免再存一份。

边界正式工程输入登记作业 `4480093.pbs-7` 已 `PASS`：49 国（不含无正式结果的 WestSahara/ESH），47 国 L2，Lesotho 和 Libya 为 L1；原源记录 56,636 条，目标行政单元 6,500 个。登记文件在 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/gadm41-admin-f0a701b-20261027/registry/`；`gadm49_registry.csv` SHA-256 为 `8cd6779106e29b4ae0dca9efe8db7670ab42e5190e62916d2eaa4c6997ad48e9`。49 国提取数组 `4480113[].pbs-7` 已提交（并发上限 4）；每国独立 GPKG 与 QC JSON 写入同一 run 根目录的 `results/admin_units/<ISO3>/`。数组提交和部分完成**不等于** 49 国最终验收。验收程序在代码提交 `d05bf13` 的独立部署根目录（同一远端前缀的 `gadm41-finalizer-d05bf13-20261027/code/`），cx3 相关测试 `15 passed`；PBS finalizer `4480160.pbs-7` 已用 `afterok:4480113[].pbs-7` 依赖提交，目前等待数组全体成功，随后检查全部 49 个源/输出哈希、层、CRS、GID、面积与样本总量。只有最终 `results/gadm49_output_manifest.json` 为 PASS 且 `results/gadm49_summary.csv` 存在才可下游使用。Kenya pilot QC 小文件已入 iCloud；其 GPKG 大文件回传遇到 VPN/SSH 中断，未宣称已入 iCloud。以上仍只是**边界输入处理**，不代表医疗人口分母或任何审稿科学重算通过。

**后续例外（覆盖上段原验收依赖）**：Ghana 第 19 项因 GADM 4.1 原始 ID 格式例外失败，原 `afterok` 验收 `4480160.pbs-7` 不会放行；详见 [GADM_GHANA_EXCEPTION_2026-10-27.md](GADM_GHANA_EXCEPTION_2026-10-27.md)。隔离补跑 `4480297.pbs-7` 已 PASS；新的合成＋终验 `4480326.pbs-7` 使用原数组 `afterany` 与 Ghana 补跑 `afterok`，以 48+1 的显式血缘建立符号链接，随后独立验收。当前终验仍待运行，**不能**将 49 国成果或医疗边界输入标记为 PASS。

刷新：原数组已完成，49 国合成成功，但 `4480326.pbs-7` 的首轮终验因 43 国 GPKG 元数据声明通用 `GEOMETRY` 而 `FAIL`（6 国通过），失败清单只有这一类。采用实际几何逐项读取的修订验收器 `af2cb23` 在 cx3 通过 10 个针对性测试；第二轮 `4480528.pbs-7` 已提交，结果将写到 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/gadm49-final-audit-af2cb23-20261027/results/`。其 manifest 未 PASS 前仍不得将任何 49 国边界文件标记为已验证。

终验结果：`4480528.pbs-7` 已 `Exit_status=0`；远端 manifest `PASS`，49/49 国、56,636 源行、6,500 个行政单元，summary SHA-256 `93b50c926a33b00f7aae4735a1ac77010c15bec7549da9b9d4061b9ece4f91bf`。各国 GPKG/QC 的远端地址由 manifest 列出。70 MB 整包已在远端打好，SHA-256 `3f80b2e38914244e5c677a5fa0a2b129420d6727bad6f1f1aee9507d7b2ae76e`，但 iCloud 回传因 SSH 复用连接卡住，**本地只有未验的 `.partial`，不能作为 iCloud 可用副本**。这是 GADM 边界输入处理 PASS，不等于 WorldPop/医疗分母、道路模型或审稿指标 PASS。

归档更新（覆盖上段失败的直连回传）：远端使用单个压缩包临时传至 Google Drive 独立目录，本机下载整包哈希一致，解包到 `~/Library/Mobile Documents/com~apple~CloudDocs/africa pavement/02_derived_checkpoints/boundaries/gadm41_admin_49country_f0a701b_gha961ead5_20261027/`。该目录内 `gadm49_output_manifest.json` SHA-256 为 `8fc06328a482befd78218a3ed4347cd9cdc012a26921017e01f962d224d23752`，`gadm49_summary.csv` SHA-256 为 `93b50c926a33b00f7aae4735a1ac77010c15bec7549da9b9d4061b9ece4f91bf`；49 个 GPKG 和 49 个 QC JSON 对 manifest 逐一核验为 `98/98 PASS`，并保留 `admin_units/lineage.json`。macOS iCloud 状态现为同步空闲、已追平，目标目录无待上传项目；未独立从云端重下载校验哈希。失败的 `.partial`、本地中转下载包、Google Drive 临时文件和空目录均已清理；远端正式成果保留。

C00 Kenya 全量 ID/几何对齐工程 pilot：代码 `751f93d`，PBS `4484004.pbs-7` `Exit_status=0`；401,965/401,965 个旧速度行与官方道路源的原始行号、表面、投影长度和中心点相符。QC 已回传至 iCloud `05_manifests/kenya_road_speed_alignment_751f93d_20261027/`，哈希/输入/限制见 [KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md](KENYA_ROAD_SPEED_ALIGNMENT_2026-10-27.md)。这只通过一个国家的旧表血缘闸门；不会触发 C02–C16 科学作业，49 国 C00 和图边 crosswalk 仍待审计。

同一 Kenya 旧速度表与投稿 `network_pipeline.py` join 代码组合诊断揭示筛选后重编号：358,791 条候选图边预计只有 1 条使用自身速度、305,759 条使用另一条源道路速度、53,031 条退回默认。该诊断经独立计数复核；五条旧图构建路径已前移道路 ID 赋值，cx3 三道路真实 Shapefile→图微测 `1 passed`。下一道单国 pilot 必须把纠正图的边 ID、实际速度 join、默认速度比例、平行边与 `p_block` 权重逐项输出，并与本诊断区分；未通过前不得批量运行城市 OD、医疗或铺装。

49 国 C00 道路输入转运（进行中）：输入登记 `audit/road_speed_alignment_registry_2026-10-27.csv` 固定 49 国、官方 RAR 大小/MD5 与旧速度 ZIP 成员；代码 `7d691fa`，转运验收脚本 `d8ddc72`。旧速度整包已在远端共享输入区复核 SHA-256 `2b1f70cbf7d079f04fe306ca683e8db115ef2539a9782fdd1ddccdca2c21589e`，Benin RAR 的官方 MD5 和大小亦通过。Benin 单国审计 PBS `4485567.pbs-7` 已提交，**结果尚未验收**。49 国 RAR 总实际 payload 为 3,368,193,081 B；rclone 共享 Google Drive 客户端在 9 个文件上传后返回请求配额 403，已停止该传输，保留完整上传项。待共享 SSH 恢复，改用可续传批量直传，并以 `hpc/verify_road_speed_transfer.py` 对远端 49 包逐件复核，正式批量数组不会在输入闸门 PASS 前提交。临时 Drive 目录待 API 恢复后清理，iCloud 原件不删除。
