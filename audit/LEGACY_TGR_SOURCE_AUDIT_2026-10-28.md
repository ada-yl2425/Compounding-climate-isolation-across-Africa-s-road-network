# C07 旧 TGR 数字来源诊断（非正式修订结果）

审稿关联：Reviewer 1 必需意见 5；Reviewer 2 次要意见 10。**本审计只追溯旧归档，不更新论文科学结论。** 修正地形、道路权重/拓扑和医疗可达性后，C07 必须使用新 C06 逐节点结果重新计算。

## 输入身份与执行

脚本：`hpc/audit_legacy_tgr_sources.py`；单测：`tests/test_audit_legacy_tgr_sources.py`。输入均直接流式读取 iCloud ZIP 成员，不在本地展开：

- `02_derived_checkpoints/legacy_reference/web_components/health_accessibility.zip`，SHA-256 `6f004995cfb8008f4a3bb811ef7d24f9df422392a83a2b42f6301ef974032d1e`；含旧版逐节点 `t_normal,t_extreme,population`，包括 WestSahara，后者不应纳入正式 49 国口径。
- `03_legacy_results/result.zip`，SHA-256 `60edcd862d5bba6484dab86a462fa7db193b71facfb691ea56ca4e3b85fdb9af`；含旧国别汇总表及 Fig. 3a 绘图表。
- `03_legacy_results/robustness_outputs.zip`，SHA-256 `27ff3ddd556943f157f862908c5ad226f4bb8683268229ec7c21b9e0cb50f6f3`；含 18 个医疗稳健性变体汇总。

诊断输出：iCloud `05_manifests/legacy_tgr_source_audit_20261028/legacy_tgr_country_diagnostic.csv`（SHA-256 `ebb808e075b50334193f6ff8b582b4835fd3c02b14fac3de4f52808153cc3ef4`）及同目录的 `legacy_tgr_aggregate_diagnostic.json`。逐国表保留数值、样本数、人口分母和表间一致性标志；输出不是修订版 TGR。

## 已验证的数字来源

| 数值 | 归档文件/代码来源 | 审计结果 |
|---|---|---|
| 主文均值 **3.60**、中位 **3.38** | `result.zip` → `result/result2/finding1_2_country_tail_gap_p50_p90_ranking/country_p50_p90_delta_travel_time_and_tail_gap.csv`；`result code/result_2a.py` 读取该绘图 CSV | 49 行的 `tail_gap_ratio_plot` 均值 **3.603918**、中位 **3.379611**，可复现原文四舍五入值。该绘图 CSV 的产生过程/源版本未确定。|
| 旧逐节点/国别汇总 TGR | `health_accessibility.zip` → 49 国节点 CSV；`result.zip` → `result/result2/country_accessibility_summary.csv`；`data_procession/compute_health_accessibility.py:496–546` | 节点 `Δt` 的人口加权 first-crossing P50/P90 在 **49/49 国**与国别汇总的 `p50_delta_h,p90_delta_h` 相符。旧汇总 50 国（含 WestSahara）的有限 TGR 均值 **17.963886**；排除 WestSahara 后 49 国只有 **24** 个有限 TGR，有限值均值 **18.643100**，不是 3.60。|
| SI S7–S8 的 **10.38–18.63** | `robustness_outputs.zip` → `robustness_outputs/08_health_variant_grid/health_variant_grid_summary.csv`；`sensitivity/health_variant_grid_sensitivity.py:532–573` | 18 个变体的 `mean_tail_gap_ratio` 最小 **10.384**、最大 **18.629**，对应 SI 两位小数。脚本对各国有效 TGR 作简单平均；不是人口加权跨国平均。|

旧绘图 CSV 的 49 行 `tail_gap_ratio_plot` 全部等于 `p90_delta_h/p50_delta_h`（若 P50=0，绘图时填为 **1**），并非从“按基准可达性定义的 P50/P90 人群”直接计算。该绘图表的 P50/P90 与逐节点归档及旧国别汇总同时相符的仅 **5/49 国**；其余 **44 国**不同。因此当前只能确认 **3.60 来自这张图表**，不能确认图表的 44 国数值使用哪个计算版本，也不能把 3.60 解释为基准可达性群组的效应。

主文“47/49 国上尾 Δt 高于中位 Δt”在绘图 CSV 的 `p90_delta_h > p50_delta_h` 比较中恰为 **47/49**。但 `tail_gap_ratio_plot > 1` 只有 **45/49**：Benin、Djibouti 的 P50=0 且 P90>0，绘图填充值为 1。不能把填充的 1 当作实测“无尾差”；分母为零的比值应保留 `NA`，并另报“P90>P50”的国家数。

## 口径分歧与正式 C07 门槛

1. Methods 定义的指标是 `Q90_pop(Δt)/Q50_pop(Δt)`；需要固定节点筛选、人口权重、不可达/缺失、零分母和国家集合。旧 `compute_health_accessibility.py` 已对零 P50 返回 `NaN`，但旧 Fig. 3a 绘图表把它填成 1。
2. Fig. 3a 文案称按**基准可达时间**的 P50/P90 人群；旧 `result2/network_buffering_decomposition.py:420–450` 实际以基准时间人口累计排序，用 P40–P60 与 >P80 节点组。此分组的群体均值 Δt 比与 `Q90(Δt)/Q50(Δt)` 是不同量，不得混名。旧逐节点表可作探索性分组审计，但缺少全部缓冲有效性过滤，不能冒充原 Fig. 3a 数值来源。
3. 正式 C07 应在新 C06 `country,node_id,t_normal,t_extreme,population,include_status` 上生成两个清楚命名的国别 CSV、跨国汇总 CSV、分母/零值账本和结果到稿件声明映射；所有表注明 run ID、代码提交、源哈希。图表 CSV 的未知版本不能作为唯一可信输入。

已验证与未确定须同时保留：**数字表内复现成立**，**图表生成血缘未证实**，**修订版结果尚未计算**。
