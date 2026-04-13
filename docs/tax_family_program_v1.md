# Tax Family Program v1

## 1. 目标

新的目标不再是“随机来一个国家就现场修 parser”，而是：

1. 先把公司支持的全部国家盘点出来
2. 按 `document/source family` 分类
3. 每个 family 先做一个可运行的基础版
4. 后续国家尽量落在已有 family 上，只做薄 overlay 或薄 pack

这样以后国家规范的小改版，才有机会由公司内部模型在 family 边界内自修，而不是每次重新写一套国家脚本。

## 2. 核心原则

### 2.1 不按国家抽通用

错误抽象：

- 一个“全球通用 parser”
- 或者每个国家一套完全独立 parser

正确抽象：

- 国家一定独立成 pack
- parser family 按 `source shape` 抽象

### 2.2 第一版 family 仍然要开发

内部模型未来能稳定处理的是：

- 同一 family 内的小改版
- 同一 family 内的新国家薄适配

内部模型不能自动替代的是：

- 新 family 的第一版设计

所以真正要投入工程的单元，不是“每个国家”，而是“每个 family 的第一个代表样本”。

## 3. 当前建议的 family 划分

先按当前真实样本，把范围收敛到 4 类：

1. `pdf_field_dictionary`
   - 强表格型 PDF
   - 字段/分组按行展开
   - 典型信号：`BT-*`、`BG-*`、cardinality/type 在同一表
   - 例子：Germany XRechnung

2. `pdf_xsd_spec`
   - 元素/属性块型 PDF
   - 典型信号：`Elemento:`、`Atributos`、`Descripción`、`Uso`、`Tipo Base`
   - 例子：Mexico CFDI Anexo 20

3. `web_drilldown_tree`
   - 官网树形语法页
   - 入口页展示节点树，但完整详情通常要点进子节点页
   - 典型信号：cardinality + node links + child pages
   - 例子：Peppol syntax tree

4. `web_inline_table`
   - 官网字段字典表
   - 主页面已经给出大部分字段列和语义
   - 允许少量字段再链接到结构页或代码表，但主数据结构不依赖逐项 drill-down
   - 典型信号：Field / Type / Mapping / Mandatory / Cardinality / Example
   - 例子：MyInvois documentation page

如果后面出现无法落进这 4 类的国家，再新开 family。不要提前为未知情况造 family。

## 4. 公司级执行顺序

### Phase 1: 全量国家盘点

先不要开发 parser，先做 inventory。

每个国家至少收这些信息：

| 字段 | 含义 |
| --- | --- |
| `country` | 国家代码 |
| `tax_domain` | 目前只填 `einvoice` |
| `official_entry_url` | 官方入口页 |
| `primary_source_url` | 当前主解析来源 |
| `source_kind` | `pdf` / `web` |
| `candidate_family` | 暂定 family |
| `language` | 文档语言 |
| `version_signal` | 页面版本号、PDF 首页日期、文件名版本等 |
| `notes` | 任何已知特殊性 |

### Phase 2: family 分桶

把全部国家按 family 分桶后，先看每桶的规模：

- 桶里国家多，优先开发
- 桶里只有 1 个国家，先确认是不是孤例

目标不是平均推进，而是先覆盖最大公共面。

### Phase 3: 每个 family 选 canonical exemplars

每个 family 先挑 1 到 2 个代表样本，要求：

- 官方源稳定
- 文档质量高
- 结构清晰
- 对这个 family 有代表性

不要一开始就挑边角料国家做 family base。

### Phase 4: 写 family base

family base 只做稳定机制：

- `pdf_field_dictionary`
  - 表格抽取
  - 行分类
  - continuation / note / path 合并

- `pdf_xsd_spec`
  - heading segmentation
  - element/attribute block grouping
  - hierarchy reconstruction

- `web_drilldown_tree`
  - DOM tree traversal
  - child-link discovery
  - detail page fetch
  - path / cardinality / description normalization

- `web_inline_table`
  - HTML table normalization
  - header aliasing
  - field row extraction
  - optional linked code/detail enrichment

### Phase 5: 国家薄适配

family base 跑通后，再给每个国家做：

- profile registry
- overlay/config
- source monitor
- fixture
- baseline

这一步才是 pack 的职责。

## 5. 接受标准

只有满足下面标准，某个 family 才算真正建好：

1. 至少 1 个 canonical country 通过 `test_extractor`
2. 至少 1 个 canonical country 通过 `quality_gate`
3. 第二个同 family 国家接入时，主要改动落在 overlay / registry，而不是 family base
4. 同一个国家小版本升级时，不需要重写 parser 主体

如果第 3 条做不到，这个 family 抽象就是错的。

## 6. 对“内部模型自己解决”的现实边界

这个目标可以成立，但边界要讲清楚。

内部模型未来适合处理：

- 官网链接变化
- 小版本 PDF 版式微调
- header marker 漂移
- note prefix 漂移
- 新国家落在已知 family 上时的薄 overlay
- 已知 drill-down 站点里的链接漂移或字段页轻微重排

内部模型不该被要求自动处理：

- 全新 family
- 来源从 PDF 变成网站或反过来
- 同一国家官方文档体系重构
- 需要新抽象层的情况

一句话：

> 内部模型能做的是 family 内自修，不是替代 family 设计。

## 7. 推荐交付物

这轮真正应该沉淀的，不只是 parser 代码，而是 3 份资产：

1. `country inventory`
   - 全部国家和官方源清单

2. `family map`
   - 每个国家归到哪个 family
   - 为什么归到这个 family

3. `family bases`
   - 每个 family 的基础版 parser

国家 pack 只是建立在这三份资产之上的执行层。

## 8. 推荐下一步

现在最应该做的不是继续扩单个国家，而是：

1. 你把公司支持的全部国家给出来
2. 我先做一版 inventory 表
3. 我按 family 分桶
4. 我给出 family 开发优先级
5. 再决定先做哪几个 family base

先把地图画对，再写 parser。

## 9. 当前已确认的两个网站样本

### 9.1 Peppol

- URL: [Peppol BIS Billing 3.0 UBL Invoice tree](https://docs.peppol.eu/poacc/billing/3.0/syntax/ubl-invoice/tree/)
- 判定：`web_drilldown_tree`

原因：

- 入口页有结构树和摘要
- 节点名称本身是可点击的
- 完整子节点详情可进入子页面继续展开，例如 `cac:AccountingSupplierParty -> cac:Party`

这类站点不能按“抓单页 HTML”处理，必须支持：

1. 发现子节点链接
2. 进入子页
3. 合并目录层和详情层

### 9.2 MyInvois

- URL: [MyInvois Invoice v1.1](https://sdk.myinvois.hasil.gov.my/documents/invoice-v1-1/)
- 判定：`web_inline_table`

原因：

- 主页面已经包含大部分字段列，如 `Field / Type / Description / UBL Schema Mapping / Mandatory / Cardinality`
- 少数字段会链接到结构页或代码表，但主体字段目录已经在主页面

这类站点优先按单页表解析，再按需补充外链字段语义。
