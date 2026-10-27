# Kenya 原始道路—旧速度表全量 ID 对齐审计

状态：**单国工程闸门 PASS；C00 全 49 国仍未完成，旧速度值的科学口径未放行。**

- 代码：提交 `751f93d` 的 `hpc/audit_road_speed_alignment.py`，按原始 Shapefile 行序生成 `Kenya_road_<row>`，仅保留 `Surface` 含 `unpaved` 且 ESRI:102022 投影长度至少 0.05 km 的线段；逐条核对旧速度 CSV 的 ID、表面、长度、经纬中心点。对应单元/回归测试本机 `49 passed, 3 skipped`，PBS 脚本为 `hpc/pbs_kenya_speed_alignment.pbs`。
- 源输入：官方 `Kenya.rar`，SHA-256 `0d441d7a8acf39d143c85e315f0447713af9c7b897a8e0596321d5553ebbb0ab`；旧 iCloud `02_derived_checkpoints/legacy_reference/road_speed_cordex.zip`，SHA-256 `2b1f70cbf7d079f04fe306ca683e8db115ef2539a9782fdd1ddccdca2c21589e`，成员 `road_speed_cordex/Kenya_road_speed.csv` 解压后 SHA-256 `7622438abe36523db8337fc1b4898fa9c5cf8f405a4277154ffffb1a88555a97`。仅为传输制作的 gzip SHA-256 `212646f449aeff694eb1317f03f1950a77f71d0f7d63ba6dbb4b0da6d712ab8c`，远端复核一致，Drive/本地临时副本已删除。
- cx3 运行：PBS `4484004.pbs-7`，`Exit_status=0`，walltime `00:39:27`，峰值内存约 700 MB；运行根目录 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/kenya-road-speed-align-751f93d-20261027-202347/`。stderr 只有模块依赖告警；stdout 记录 `KENYA_ROAD_SPEED_ALIGNMENT_PASS`。
- 结果：原始道路 **504,366** 条，其中 `unpaved` **431,865** 条；其中长度小于 0.05 km 的 **29,900** 条，故应进入速度表 **401,965** 条。旧速度表恰有 **401,965** 个唯一 ID，逐条 ID 匹配 **401,965/401,965**；重复 ID、缺失/额外 ID、长度/中心点不一致、表面不一致、无效几何均为 **0**。
- QC JSON SHA-256 `41a7a9e85f8925098d800f7d99103f9558cea4651892307ea9825d2dd772210f`，iCloud 归档：`africa pavement/05_manifests/kenya_road_speed_alignment_751f93d_20261027/kenya_speed_alignment_qc.json`；同目录保存 PBS stdout/stderr。远端正式 QC 保留在上述运行根目录的 `results/`。

该 PASS 只证明 Kenya 的**旧速度 CSV 与官方源道路的行号/几何/筛选血缘一致**。不证明旧气候文件、坡度/曲率、MGD/IRI、通行率、图权重或审稿新结果正确。下游几个网络/医疗脚本在筛选后重新编号，道路 ID 错配风险仍然存在；继续按 C00 审计其它正式国家和图边 crosswalk，不能据此勾选 C00 或放行 49 国科学数组。

## 旧图 join 的独立诊断

`result1/network_pipeline.py` 先按 0.1 km 筛选、`reset_index(drop=True)`，再从 0 重建 `Kenya_road_<index>`；旧速度表则按原始源行号编号且阈值为 0.05 km。以已通过上段全量对齐的 Kenya 速度表重演这两条确定规则，358,791 条符合旧图阈值的未铺装边中，**1** 条图边会连到自身速度行，**305,759** 条会误连其它源道路的速度行，**53,031** 条无相同编号速度行而走默认速度；误连中 288,514 条的两条道路长度相差超过 10%。两种独立计数实现得到相同的 `401965,358791,1,305759,53031`。诊断程序见代码提交 `491c30f` 的 `hpc/audit_legacy_graph_reindex.py`；JSON 位于 iCloud `africa pavement/05_manifests/kenya_graph_reindex_diagnostic_491c30f_20261027/legacy_graph_reindex_diagnostic.json`，SHA-256 `6a94263e54b6860dfafe82eaa33ea50d3b645acd1d0254a51f347eb567e9a165`。

这是**基于投稿代码与旧速度表推算的 join 诊断**，前提是旧图实际读取相同的道路顺序；没有直接读取历史图 checkpoint，也没有计算 OD/医疗/干预误差，故不能把上述条数称作历史论文结果的已量化偏差。但该代码路径必须修复并重新运行受影响的网络下游。五个旧图构建器已改为**读取源文件后、任何筛选前**赋予道路 ID。本机 `57 passed, 3 skipped`；cx3 在隔离代码根目录 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/kenya-graph-id-test-491c30f-20261027-222221/code/` 运行真实三道路 Shapefile→图构建测试 `1 passed`，确认筛掉第一条铺装路后，保留道路仍使用原始 `Kenya_road_1/2` 与各自速度。仍需全 Kenya 更正图的端到端 QC；平行边、通行率双重惩罚等独立卡点未解决。
