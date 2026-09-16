# SERBench：找回当前决策仍然缺少的证据

[English](README.md) · [论文](docs/paper.pdf) · [数据说明](docs/DATASET.md) · [评测流程](docs/EVALUATION.md)

SERBench 面向编码智能体，评测的不是“某段内容是否相关”，而是“返回的证据组合是否覆盖当前决策尚缺的必要信息”。本仓库提供便于加载的数据、严格的预测校验、官方评分逻辑及可直接运行的基础示例，不是 OpenReview 实验复现包的简单镜像。

## 开始使用

需要 Python 3.10 或以上。核心接口不需要外部模型 API。

```bash
git clone https://github.com/LordTARN1SHED/SERBench.git
cd SERBench
python -m pip install -e .
python -m serbench inspect --split example
python -m serbench baseline --split example --output predictions.jsonl --k 8
python -m serbench score --split example --predictions predictions.jsonl --k 5 8 --output example_scores
```

示例来自三个真实 Cal500 状态，只用于验证流程。附带的轻量 BM25 是接入示例，不是论文中冻结 BM25 实验的复现版本。完整开发评测请将 `example` 换成 `cal500`。

## 数据与评测边界

| 数据集 | 状态 | Issue 实例 | 仓库 | 证书 |
|---|---:|---:|---:|---|
| Cal500 | 500 | 241 | 174 | 公开，用于开发与校准 |
| Test500 | 500 | 242 | 45 | 作者保管，用于留出评测 |

候选池可以包含已观察条目，但证书仍定义当前缺失的支持。评分保留原始返回顺序：已观察条目占用位置，不会自动删除并递补。Cal500 是机器校准并跨模型修复的标注，不应表述成与 Test500 相同的独立人工裁决数据。

Test500 请先在本地校验预测，再按[评测说明](docs/EVALUATION.md#held-out-test500-evaluation)提交 GitHub 评测请求。私有评测任务启用后定时处理并回复汇总分数，不公开隐藏标签。网站显示服务状态；启用前可联系 **zhf023@ucsd.edu** 由作者协助评分。预测文件和评测请求公开，机密预测请勿提交到公开 Issue。

论文在 Test500 上的 Complete-MSS@5 / @8：MSS-Complement 为 **73.0% / 80.6%**，Qwen3 embedding with reranking 为 **61.4% / 72.4%**。这些是论文参考结果，不是示例运行结果。

## 引用与许可

引用格式见[英文首页](README.md#cite-serbench)。原创代码采用 MIT；原创标注与状态材料按 CC BY 4.0 发布；上游源码、Issue 文字等仍遵守各自的原始权利与许可，详见 [DATA_LICENSE.md](DATA_LICENSE.md)。
