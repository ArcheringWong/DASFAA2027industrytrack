# D3 证据审计

## 证据链

| 事项 | 直接证据 | 层级与限制 |
|---|---|---|
| 性质先于自动代码冻结 | `D3_METAMORPHIC_SPEC.md`、`D3_EXPERIMENT_PROTOCOL.md` | 条件化非新增输出前缀；两种合法性证据；非法情形与状态在真实自动运行前写定 |
| 自动化前手工配对 | `manual_pairs.py`、`evidence/manual_pairs_1.31.0.json`、`manual_pairs_1.32.0.json` 与原始控制台 | 真实 dlt→内存 DuckDB；两个输入各自独立 pipeline；仅校准，不算自动生成 |
| 规则生成与合法性判定 | `make_cases.py`、`cases.json`、`metamorphic.py` | `prefix_recipe` 仅写中性证据和数量，程序从 prior 选旧边界或分配新的空游标 ID；自动拼接批次；没有 Issue 编号分支 |
| 真实自动配对和状态 | `evidence/metamorphic_1.31.0.json`、`metamorphic_1.32.0.json`、对应 `*_console.txt` | 每个合法输入保留原始/变形批次、请求批次、目标行、state 和错误；零输出且无表视为空确认集合 |
| 独立文件复核 | `verify_evidence.py`、`evidence/summary.json`、`verification_console.txt` | 对两个机制的手工/自动目标和页请求一致性、全部状态、oracle 等价、12 个非法案例未执行作断言；代码 SHA-256 在 summary |
| 环境 | `evidence/requirements_131.lock`、`requirements_132.lock`、`pip_*.log`、`environment.json` | 本地真实发布包、Python 3.11.4、dlt 1.31.0/1.32.0、DuckDB 1.5.6、PyArrow 26.0.0；无外部服务 |

D0–D2 原始数据与代码没有写入。本轮对两个已知 Issue 的结论需回溯到 [D1 四步结果](../D1_domain_testing/D1_RESULTS.md)、[D2 Arrow 校准](../D2_cross_mechanism/D2_RESULTS.md) 及公开 [#4523](https://github.com/dlt-hub/dlt/issues/4523)、[#4284](https://github.com/dlt-hub/dlt/issues/4284)。D3 新实验只算手工成对预检与自动变形运行，不把 D1/D2 的旧结果改记为新发现。

## 限制和反误报

- 仅受控合成源可证明所有批次覆盖完整、所有记录在同步前可见、同游标顺序稳定。`source_complete` 与 `stable_ties` 是案例明确声明并在本地构造中可审计的前提；若外部 API 无此保证，不能直接应用性质。
- 边界基线第二轮只提供新 `id2`，变形加入旧 `id1`；这要求源 API 允许不重发已经确认的旧身份，同时保证全部新合格身份。dlt 自定义 resource 支持两种输入；若某真实源强制重发所有旧行，应另选合法基线，不能照搬。
- 空游标前缀在 `exclude` 下才中性；`include` 对照被拒绝。空值插在升序非空序列前，不改变有效游标排序。`NULL` 的数据库排序规则未被假定；输入是受控 Arrow 批次而非 SQL 无序扫描。
- 目标 ID 集合支持 at-least-once 完整性判断；`merge`/upsert 可掩盖重复发射，因此没有 exactly-once、重复次数或中间 dlt 输出层的结论。候选运行保留源请求与目标行，未直接钩取过滤器之后的逐条输出。
- 1.31.0 的基线本来就漏数时返回 `INCONCLUSIVE`，没有把已有失败归因于前缀；12 个非法变形在产品调用前被拒绝；本次 `EXECUTION_ERROR=0`，分支未观察到真实异常。13 个正常对照均 `PASS`，**不等于总体误报率为零**。
- #4284 仍无正式修复版，D3 只在 1.32.0 对照原始/变形；没有声称检查点推进。两类机制都来自 dlt，不能外推跨产品。

自动框架开发中曾为加强边界中性验证和改成程序生成前缀重复运行同一有限案例集；`evidence/metamorphic_*.json` 是最终代码的最后一轮原始轨迹。早期开发运行未保存为独立样本，不能用于统计或声称重复实验的独立性。手工成对预检文件保留其先于自动框架的独立执行。没有为追求更高命中率重调随机权重；D3 不做随机命中率实验。
