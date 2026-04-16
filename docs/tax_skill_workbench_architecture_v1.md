# Tax Skill 工作台架构说明 v1

## 1. 文档目的

本文档描述当前 tax skill 工作台的实际运行原理，重点回答这几个问题：

1. `core`、`pack`、`parser`、`harness`、`monitor` 分别是什么
2. 一份 PDF 从输入到产出是怎么流动的
3. 新国家接入时应该改哪一层，不该改哪一层

本文档描述的是当前仓库中已经落地的结构，而不是早期单 skill 方案。

## 2. 总体结论

当前工作台不是“一个大 skill + 多个脚本”的结构，而是：

- 一个稳定的 `tax-parser-core`
- 多个国家或税种 `tax-pack-*`
- 一个统一的验证与监控闭环

也就是：

- `pack` 负责国家差异
- `core` 负责通用执行工作台
- `parser` 负责 PDF 字段抽取
- `harness` 负责规则与验收
- `monitor` 负责官方源变化发现

## 3. 分层结构

### 3.1 分层图

```text
用户 / 自动化
  -> pack
  -> core runtime
  -> parser
  -> output
  -> harness

官方源
  -> monitor
  -> followups
  -> core runtime
```

### 3.2 五层职责

#### A. Pack Layer

这是国家包入口层。

它的职责是：

- 提供国家或税种自己的 `profiles`
- 提供自己的 `sources`
- 提供自己的 `baselines`
- 通过 `pack_cli.py` 调用旁边安装好的 `tax-parser-core`

典型目录：

- [skills/tax-pack-rs-einvoice](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-rs-einvoice)
- [skills/tax-pack-hr-einvoice](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-hr-einvoice)

典型入口：

- [skills/tax-pack-rs-einvoice/scripts/pack_cli.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-rs-einvoice/scripts/pack_cli.py)

#### B. Runtime Layer

这是通用运行时层。

它的职责是：

- 读取 registry
- 自动选择 extractor / profile
- 调用具体 parser
- 写出标准输出文件
- 跑 test / monitor / followups

核心文件：

- [skills/tax-parser-core/tax_parser_runtime/runner.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-parser-core/tax_parser_runtime/runner.py)
- [skills/tax-parser-core/tax_parser_runtime/testing.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-parser-core/tax_parser_runtime/testing.py)
- [skills/tax-parser-core/tax_parser_runtime/monitoring.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-parser-core/tax_parser_runtime/monitoring.py)
- [skills/tax-parser-core/tax_parser_runtime/followups.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-parser-core/tax_parser_runtime/followups.py)

#### C. Parser Layer

这是实际的字段抽取层。

它由两部分组成：

- family parser
- 国家 overlay

其中：

- family parser 负责通用文档族逻辑
- overlay 负责国家级差异

典型文件：

- [skills/tax-parser-core/tax_parser_runtime/families/en16931_ubl/base.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-parser-core/tax_parser_runtime/families/en16931_ubl/base.py)
- [skills/tax-pack-rs-einvoice/profiles/overlays/rs_overlay.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-rs-einvoice/profiles/overlays/rs_overlay.py)
- [skills/tax-pack-hr-einvoice/profiles/overlays/hr_overlay.py](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-hr-einvoice/profiles/overlays/hr_overlay.py)

#### D. Harness Layer

这是治理和验收层。

它不负责抽字段，而负责判断：

- 这次改动是否在允许范围
- 这次输出是否达到可接受标准

核心文件：

- [scripts/harness/security_guard.py](/Users/xueyunsong/Documents/GitHub/gec-ai/scripts/harness/security_guard.py)
- [scripts/harness/quality_gate.py](/Users/xueyunsong/Documents/GitHub/gec-ai/scripts/harness/quality_gate.py)

可以把它理解成 parser 工作台里的“本地 CI 护栏”。

#### E. Monitor Layer

这是官方源变化监控层。

它的职责是：

- 盯官方 landing page
- 盯附件 checksum
- 盯版本信号
- 产出 review item 和 follow-up

典型文件：

- [skills/tax-pack-rs-einvoice/sources/official_sources.yaml](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-rs-einvoice/sources/official_sources.yaml)
- [skills/tax-pack-hr-einvoice/sources/official_sources.yaml](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-hr-einvoice/sources/official_sources.yaml)

## 4. 一份 PDF 的执行路径

### 4.1 正常解析路径

输入一份 PDF 后，执行路径如下：

1. 用户运行国家 pack 的 `pack_cli.py`
2. pack CLI 把任务转发到 `tax-parser-core`
3. `core` 根据 `--pack-dir` 读取 pack 自己的 registry
4. `runner.py` 自动选 profile，或使用显式指定的 extractor
5. `registry.py` 解析出对应 overlay / module / baseline
6. overlay 调用 family parser 或 legacy parser
7. parser 产出标准记录
8. runtime 写出：
   - `field_catalog.json`
   - `field_catalog.csv`
   - `run_report.json`

### 4.2 测试与收口路径

当执行 `test` 或 `quality-gate` 时，工作台会追加验证链路：

1. `py_compile`
2. parser run
3. output validate
4. baseline compare
5. quality gate 判定 `pass / fail`

`quality_gate.py` 会读取 registry 中的 `stability`：

- `stable` 需要 baseline diff 满足阈值
- `experimental` 则允许作为试验 profile 继续迭代

## 5. Registry 的角色

`registry` 是 pack 和 runtime 的连接层。

它解决的问题是：

- 这个 pack 里有哪些 profile
- 每个 profile 对应哪个 module
- 默认 baseline 在哪
- 自动识别 hint 是什么
- 这个 profile 是 `stable` 还是 `experimental`

典型文件：

- [skills/tax-pack-rs-einvoice/profiles/registry.json](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-rs-einvoice/profiles/registry.json)
- [skills/tax-pack-hr-einvoice/profiles/registry.json](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-hr-einvoice/profiles/registry.json)

## 6. Overlay 和 Family 的边界

### 6.1 Overlay 应该放什么

适合放在 overlay 的内容：

- header markers
- note prefixes
- 文档族的小范围配置差异
- 国家级命名、路径或结构特征

### 6.2 Family 应该放什么

适合放在 family parser 的内容：

- 多个国家共享的表格结构识别逻辑
- 行类型识别逻辑
- 通用路径块处理
- 通用字段合并逻辑

### 6.3 不该怎么做

不应该：

- 为了一个国家的小问题去改 `core`
- 为了复用已有国家包直接复制一整份旧 pack 然后慢慢删
- 把跨国家的共性逻辑长期堆在 overlay 里

## 7. Harness 怎么理解

`harness` 不是 parser 的一部分，而是 parser 工作台的规则执行层。

它的角色像本地 CI：

- `security_guard.py` = 改动范围护栏
- `quality_gate.py` = 输出质量护栏

也就是说：

- parser 负责“能不能抽出来”
- harness 负责“能不能算通过”

## 8. Monitor 和 Followups 的闭环

监控层不是简单抓页面，而是为了触发解析闭环。

完整路径是：

1. `official_sources.yaml` 定义官方锚点页和附件
2. `monitoring.py` 抓取 landing page / attachment
3. 生成：
   - `snapshot`
   - `change_report`
   - `review_items`
   - `followups`
4. `followups.py` 决定是否自动重跑：
   - `test_extractor`
   - `tax_pipeline`
   - 或人工建议命令

所以监控层不是“搜最新税法”，而是“对一份人工维护的官方源清单做自动观察和续跑”。

## 9. 新国家接入时应该改哪层

### 9.1 大多数情况

大多数新增国家应该只改 pack：

- 新建 `skills/tax-pack-<country>-<domain>/`
- 填 `pack.json`
- 填 `profiles/registry.json`
- 写 overlay
- 写 `official_sources.yaml`
- 准备 baseline 和 fixture

### 9.2 少数情况

只有在文档结构明显不属于现有 family 时，才应该去改：

- `skills/tax-parser-core/tax_parser_runtime/families/...`

### 9.3 不该直接改的层

除非有明确理由，不应先改：

- `skills/tax-parser-core/scripts/...`
- 通用 runtime 入口
- 其他国家 pack

## 10. 当前推荐理解方式

可以把整个工作台概括成一句话：

> `pack` 管国家差异，`core` 管执行，`parser` 管抽取，`harness` 管验收，`monitor` 管变化发现。

这五层分开后，才有可能做到：

- skill 变小
- 新国家可复制接入
- 风险隔离
- 自动监控后可续跑
- stable / experimental 有清晰边界
