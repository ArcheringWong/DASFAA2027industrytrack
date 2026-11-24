# D4 初始 A/B/C 实现与成本

任务和协议在代码结果前冻结，见 `D4_MAINTENANCE_TASKS.md`、`D4_EXPERIMENT_PROTOCOL.md`。D3 `metamorphic.py` 原样复制为 D4 `engine.py`（257 物理行）；它同时提供真实 dlt→内存 DuckDB 适配器、源身份 oracle、C 的中性前缀生成与验证。A/B 仅调用其中 `run_product` 和独立 `expected_ids`，不调用 C 的 `validate`/`test_pair`。`common.py`（48 行）为 A/B 提供单场景判定及统一轨迹；这些公共代码的建立和维护成本不可算成 C 免费资源。冻结代码副本在 `snapshots/base/code/`。

| 方案 | 初始专有实现 | 初始输入与测试方式 | 已知故障/正常/无效 |
|---|---|---|---|
| A | `test_a.py` 17 行，8 个显式历史配置 | 参数化 pytest；共享适配器和身份 oracle；每个历史跑一个真实场景 | 1.31 边界遗漏、1.32 Arrow 遗漏均检出；修复边界、同页、无前缀、空值后置、无排序通过；`include` 中性声称拒绝 |
| B | `stateful_b.py` 93 行，8 个显式种子配置 | 确定性回放保证同等验收；`RuleBasedStateMachine` 另以选择历史、拆批、合批、去除排除空前缀和 oracle 不变量运行最多 4×3 步探索 | 确定性部分与 A 同结果；最终代码两版各产生 10 个真实状态机评估，不将它们当新 Bug 或公平命中率样本 |
| C | `run_c.py` 26 行，8 个基础历史＋前缀配方配置；另使用 D3 引擎中的统一关系实现 | 每合法实例两个独立真实场景，先核对中性合法性、再分别用源 oracle 判定 | 与 A/B 同故障及对照；1.31 基线自身漏数判 `INCONCLUSIVE`；非法变形不调用产品 |

初始案例按版本展开 1.31.0 四个、1.32.0 七个。A/B 的同一案例配置是可读的完整源历史，C 的是基础历史和中性配方；三者不共享专有案例文件。所有方案共享真实产品版本、源身份 oracle、目标读取和诊断字段。初始 A/B/C 六次套件命令均退出 0；原始输入、输出、请求页、state、耗时和异常在 `evidence/base/`。B 的额外生成运行应单独计费，不与 A/C 的固定回归耗时直接排名。

初始代码量不能只看 A17/B93/C26：`engine.py` 257 行、`common.py` 48 行，其中 `engine.py` 的 `flatten`、`expected_ids`、`run_product` 函数定义合计 74 行是共用适配与 oracle；`common.py` 48 行主要服务 A/B。`engine.py` 的 `ordered`、`derive_prefix`、`transformed_batches`、`validate`、`test_pair` 函数定义合计 125 行专属 C，另有 26 行 C 包装器；其余为导入、常量和 D3 自带 CLI。三种方案都享有共享基础设施，也都应计入它的初始建立和后续修改成本。D4 复制 D3 已完成的代码，记录的是可复核实现规模，不是本阶段人类工时。
