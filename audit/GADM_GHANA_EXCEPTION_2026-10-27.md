# GADM 4.1 Ghana ID 例外与隔离补跑

状态：输入工程修复，**不是**审稿科学指标。原始全球 GADM 源、49 国登记和其余国家输出均未修改。

- 原数组 `4480113[].pbs-7` 的第 19 项 Ghana 因旧校验要求 `GHA.` 前缀失败（`Exit_status=1`）。原始 GADM `gadm_410.gpkg` 中该国 260/260 个 L2 ID 使用 `GHA1.1_2` 等无点分隔的格式；260/260 个 L1/L2 ID 都符合 `GHA[0-9]+(?:[.][0-9]+)*_[0-9]+`，`GID_0` 均为 `GHA`。全球源的非点前缀异常国还有 CHN、UKR，**不在**正式 49 国集合。源记录并非 Ghana 缺失。
- 代码提交 `961ead5` 只为 `GHA` 接受该精确格式；其它国家仍要求 `ISO3.`，错误的外来国家 GID 测试仍须报错。cx3 提取测试 `6 passed`，本地全套 `43 passed, 2 skipped`。
- 独立修复 PBS `4480297.pbs-7` 已 `Exit_status=0`。Ghana QC 为 `PASS`，260 源记录、260 个 L2 行政单元；GPKG SHA-256 `63932a5282c1d49bb6db405835960280e1b4ac249a66990e9737bfae03fb63cc`。产物在 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/gadm41-gha-repair-961ead5-20261027/results/admin_units/GHA/`。
- 原始数组继续至全部 49 项结束；不能因修复 Ghana 成功就宣称 49 国通过。隔离合成作业 `4480326.pbs-7` 依赖原数组完成及 Ghana 补跑成功；它只以符号链接组合原数组成功的 48 国和新 Ghana，再独立执行 49 国哈希、GPKG schema/CRS/GID/面积终验。合成目录 `/rds/general/user/yl2425/ephemeral/africa_pavement_recalc/gadm49-overlay-390d63e-20261027/results/`；最终 `gadm49_output_manifest.json` 为 `PASS` 且 `gadm49_summary.csv` 存在以前，不供医疗或人口计算使用。原先要求原数组全成功的 `4480160.pbs-7` 在 Ghana 失败后不会放行，不得引用为验收结果。
