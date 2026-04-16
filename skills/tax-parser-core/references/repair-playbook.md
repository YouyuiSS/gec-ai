# Repair Playbook

这份 playbook 不是解释概念，而是告诉 OpenCode agent 在 parser 结果不对时该怎么改。

## 1. 总原则

先跑，再判断，再改，再回归。

固定顺序：

1. 跑 `run_tax_parser.py`
2. 跑 `test_extractor.py`
3. 如果失败明显，再跑 `repair_extractor_brief.py`
4. 按下面的分诊规则决定改哪一层
5. 改完后重新跑 `test_extractor.py`
6. 只有回归通过后，才允许晋升 baseline

不要跳过测试直接 promote baseline。

## 2. 先改哪一层

优先级固定如下：

1. `profiles/registry.json`
2. 对应 `overlay.py`
3. `family base.py`
4. `extractors/` 兼容层

默认规则：

- 如果只有一个国家坏，先改 overlay
- 如果多个 overlay 出现同类结构问题，才改 family base
- 如果是选错 profile，先改 registry hint，不要先改 parser
- `extractors/` 只做兼容，不要把新逻辑继续堆在里面

## 3. 常见症状怎么修

### 3.1 根本选错 parser

信号：

- auto-select 命中错误 profile
- `record_count` 明显离谱
- `missing` / `extra` 非常高
- 第一页关键词明明不匹配，却还是命中

优先检查：

- `profiles/registry.json`
- `filename_contains`
- `text_contains`

动作：

- 先调 registry hint
- 不要先改 family base

### 3.2 字段总数不对

信号：

- `missing_count` 很高
- `extra_count` 很高
- 大量 `BG-*` 被当成字段
- 明显表头、目录行被当成数据

优先检查：

- family base 的 header 过滤
- `BT-* / BG-*` 识别规则
- 表格起始行和 continuation 行识别

动作：

- 多国家同类问题：改 family base
- 单国家格式偏差：先改 overlay 的配置

### 3.3 路径丢了或路径只到父节点

信号：

- `invoice_path` / `credit_note_path` 大面积为空
- 路径只到 `.../Contact`，没有 `cbc:*`
- `path_coverage_ratio` 很低

优先检查：

- family base 的 path stitching
- 路径续行拼接
- 是否把 `/cbc:*` 当成新路径或普通文本

动作：

- 这是 family base 优先问题
- 修完后抽样看至少 3 个字段的 invoice / credit note 路径

### 3.4 `@schemeID` 污染上一字段

信号：

- 当前 BT 的 path 变成 `.../@schemeID`
- note 里混入 `Invoice/.../@schemeID`
- 实际应属于后面的匿名 `Scheme identifier` 子字段

优先检查：

- family base 是否能识别匿名 subfield 行
- 是否在进入 `Scheme identifier` 时先结束上一条 BT

动作：

- 先改 family base
- 回归看相邻字段是否恢复

### 3.5 名称和描述错位

信号：

- `field_name` 里混进英语残片
- `field_description` 只剩半句
- 本地语言和英语拆分不稳定

优先检查：

- family base 的 semantic name parser
- overlay 的本地语言修正

动作：

- 单国家语言问题：先改 overlay
- 多国家共性拆分问题：再改 family base

### 3.6 只有某些字段坏

信号：

- 总体结果正常
- 只有少数 `BT-*` 字段名、描述、note 或路径有偏差

动作：

- 优先做 overlay 级 fixup
- 不要为了几个字段去动 base

## 4. 改完后必须看什么

至少看这 4 个维度：

1. `record_count`
2. `missing / extra / changed`
3. 关键坏样本字段抽样
4. `run_report.json` 里的 `extractor_family`、`jurisdiction`、`registry_source`

抽样时至少检查：

- 一个普通字段
- 一个跨页字段
- 一个带 `@schemeID` 的相邻字段组
- 一个长路径字段

## 5. 什么时候允许 promote baseline

必须同时满足：

- `compile` 通过
- `run` 通过
- `validate` 通过
- 有 baseline 时，`compare` 结果可接受

推荐规则：

- 已成熟 profile：`changed=0` 再 promote
- 新接入国家的首次基线：人工确认后再 promote
- 不要用明显脏结果覆盖 baseline

## 6. 不要这样做

- 不要先改一堆文件，再第一次跑测试
- 不要在没有证据时直接动 family base
- 不要把脚本再改回“自己调模型修代码”
- 不要用一份新 PDF 结果直接覆盖旧国家 baseline

## 7. 最小修复闭环

当结果不对时，最小闭环就是：

1. 跑 `test_extractor.py`
2. 跑 `repair_extractor_brief.py`
3. 决定改 registry / overlay / base 哪一层
4. 改一个小点
5. 再跑 `test_extractor.py`
6. 看 diff 是否收敛

一轮只改一类问题，比一次改很多处更稳。
