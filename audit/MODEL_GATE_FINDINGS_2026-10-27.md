# G0 模型口径闸门：已证实的行为与待决科学解释

状态：2026-10-27。以下是代码／主文／SI 的静态核对，不是新科学结果，也没有据此修改模型参数。需要先冻结下列选择，再运行 G2 道路速度和 G3 图。

| 项 | 已证实的行为 | 决策／测试卡点 |
|---|---|---|
| IRI 的 12.0 | 主文把 12 称作 equilibrium target 的下限，`compute_road_speed.py` 使用 `max(f(...),12)`；SI S2 的 “Maximum roughness cap” 与数学含义相反。起始 IRI=6，故 12 不是每个时步 IRI 状态的即时下限 | 先修正文/SI 标签；以 `f=10→12`、`f=15→15` 做边界测试。仅标签错误不能自动宣称要重算 |
| MGD | 投稿所用公式与 [Paterson 原研究（TRB, 1991）](https://onlinepubs.trb.org/Onlinepubs/trr/1991/1291vol1/1291-056.pdf) 相同；原文把 `MGD` 定义为路面材料 dust ratio `P075/P425`（或特殊情况下为 1），**无量纲**，不是主文/SI 所称 mean gravel depth `0.5 m`。代码设 `MGD=0.5`，其平方项恰为零 | 参数名称/单位和来源**确定需要更正**；0.5 可以是统一 dust-ratio 假设，但原道路无粒径筛分证据，不能称实测砂砾深度。单凭此写作误定义不能断定旧数值错误；用 0.4/0.5/0.6 的 fixture 测试 |
| 衰减时间单位 | 上述 Paterson 公式明确 `T` 为两次平整养护之间的**天数**；当前 `HDM4_DT=1/12` 被直接乘入同一指数项，并重复 12 次 | 相对所引原公式，这是**确定的量纲冲突**。必须先确定采用 Paterson 早期式还是有重新标定系数的 HDM-4 版本，以及如何把养护间隔映射为本研究情景；不可未经科学决定机械替换成 30 并批算。此项很可能触发整链重算 |
| 降水月长 | CORDEX `pr` 是 `kg m^-2 s^-1` 的月平均通量；基准和未来代码都乘 `86400×30`，实际月份为 28–31 天 | 这是对“月总降水”定义的**确定数值偏差**；须按 NetCDF 日历／`time_bnds` 决定转换，并用 28/31 天恒定通量测试 |
| 月度迭代 | 代码先把 120 月汇成均值/P95，然后用同一数值重复 12 次，不是逐月 120 次递推 | 冻结论文究竟要“代表月×12”还是实际逐月递推；两个月雨量调换顺序的 fixture 区分方法。不先验把新算法调到旧结果 |
| 未来时间窗 | 默认 `period±5` 且包含端点，2045 对应 2040–2050 共 11 年；论文示例 2041–2050 为 10 年 | 精确列出每期 120 个月与所用成员后再批算；旧运行参数/日志若找不到，不把旧速度表视作论文时窗已证实 |
| 通行率 `r` | 主文 Eq.4、Eq.8 与代码一致：速度先乘 `r`，极端图权再除 `1-p_block=r`。若同一概率代表同一机制，净效应为 `1/r²` | **双次应用是确定的，是否不合理属待决模型语义**。须说明两项是否代表独立机制；微型例 `L=10 km,V_base=60 km/h,r=.5`：一重为 0.3333 h、现实现为 0.6667 h。决定后统一各图／医疗／干预代码与 SI |
| 平行边 | 图构造按最小正常权重把相同端点的物理路段合成一条 `nx.Graph` 边；可能丢失极端条件下更快的替代路段，且替换时有边元数据未同步更新 | 用 A(`w0=1,w1=100`) 与 B(`w0=2,w1=3`) 双平行边 fixture；选定保留物理多边还是显式做同 OD 双情景映射，并验证 `canonical_edge_id,length_km` |
| 样本与人口回退 | 旧非洲城市档有 84 节点，去 ESH 是 83；医疗代码在栅格失败时可把每节点人口设为 1 | 正式国别/OD 排 ESH，另决定其路段是否允许作过境；输入缺失必须 fail closed，人口不能用 1 虚构。人口分母守恒需单测 |
| 地形变量实际进入速度 | Kenya Figshare RAR 经 cx3 解压抽检：504,366 条 LineString，EPSG:3857，属性仅 `ID,Rd_length,Surface,Start_pt,End_pt`，**无** `slope_deg` 或 `curvature_deg_km`；投稿 `compute_road_speed.py:297-300` 对缺列补 `0.0`。旧 `Kenya_road_{0,8,12,16}` 速度 CSV 的长度和经纬中心点与该 RAR 按投稿投影算法重建的值逐项精确吻合（长度误差约 1e-11 km），强烈支持旧速度表使用同一几何和同一 ID 规则 | 若投稿正式运行确实直接读取此 RAR，则 Kenya 速度的坡度/曲率项就是零；但仍需核旧运行是否曾在读取前为相同几何增加过属性，不能仅凭汇总结果证明全 49 国情形。要重建则须先确定坡度单位/DEM 来源，并从道路几何算曲率；全球覆盖且无单位标签的归档坡度 TIFF 不能直接代替已验证字段 |

原始路径：`data_procession/compute_road_speed.py`、`data_procession/future_road_speed.py`、`result1/network_pipeline.py`、`result1/run_africa_layer.py`、`data_procession/compute_health_accessibility.py`；审稿原文及输入见 [REVIEWER_RECALCULATION_CHECKLIST.md](REVIEWER_RECALCULATION_CHECKLIST.md)。Paterson 原研究 PDF 已由官方 TRB 站点文本核对；它记录的是投稿公式的原始经验模型，并不自动证明投稿应将其称作哪一版 HDM-4，须再核对所引手册版本。

**G0 尚未 PASS**：这些是已找到的冲突及明确待决问题，不是已经选择的修正模型。不能启动正式 cx3 科学数组或将旧结果标为验证通过。

cx3 工程证据：Kenya RAR schema 作业 `4479850.pbs-7`，`Exit_status=0`；结构报告 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/pilot-20261027-e3bd600/results/kenya_road_schema_qc.json`。此状态只证明该包可读与字段构成，不证明路网拓扑、原稿版本一致性或路段空间真实性。

四路段 ID/几何抽样对齐报告：同目录 `results/kenya_road_alignment_samples.json`，SHA-256 `2eadeee70a1e188d2d150337f917d30a8fb10ea4c993b38115ffcc1678707401`。对照旧 iCloud `02_derived_checkpoints/legacy_reference/road_speed_cordex.zip` 内 `road_speed_cordex/Kenya_road_speed.csv` 的四行；此为历史数据血缘核查，不是新科学速度结果。
