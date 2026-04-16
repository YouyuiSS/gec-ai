# 原文件批注反馈教程 v1

这份文档讲的是：当 parser 结果有问题时，怎么直接在原文件上做批注，让 AI 后续能稳定看懂并修。

目标不是让评审人写规则总结，而是让评审人：

1. 直接指出哪里错
2. 说明应该怎么取
3. 留下可回看证据

## 1. 适用场景

适用于两类 source：

- PDF 规范
- 网站规范的快照文件

注意：网站不要直接批注线上页面。先把页面存证，再批注存证文件。

推荐存证方式：

- 单页字段表网站：打印成 PDF 再批注
- drill-down 网站：把入口页和详情页分别打印成 PDF 再批注

## 2. 核心规则

### 一条批注只表达一个问题

不要在一条批注里同时写：

- 漏抽
- 路径错
- 必填性错

一条批注只写一个问题，后面才好转结构化数据。

### 先圈证据，再写结论

每条批注都应该有两部分：

1. 批注锚点
   - 高亮、框选、下划线都可以
2. 批注正文
   - 写清“哪里错”和“应该怎么取”

### 用固定短语，不要自由发挥

批注开头统一用这几类之一：

- `漏抽`
- `多抽`
- `路径错`
- `基数错`
- `类型错`
- `合并错`
- `说明串脏`
- `详情漏跟`

## 3. 推荐批注格式

每条批注正文尽量按这个格式写：

```text
问题类型：路径错
字段：BT-82
当前结果：/Invoice/cac:AccountingCustomerParty/cbc:EndpointID
正确结果：/Invoice/cac:AccountingCustomerParty/cac:Party/cbc:EndpointID
怎么取：这里要保留父节点 cac:Party，不能跳级
```

如果懒得写全，至少保留这 3 行：

```text
问题类型：基数错
字段：BT-24
怎么取：这里是 mandatory，应取 1..1
```

## 4. PDF 批注教程

### 场景 A：字段漏抽

做法：

1. 高亮字段标题或字段所在行
2. 写批注：

```text
问题类型：漏抽
字段：BT-146
怎么取：这一行也要出现在 field_catalog 里
```

### 场景 B：路径抽错

做法：

1. 框选路径证据，通常是字段所在表格行或结构树
2. 写批注：

```text
问题类型：路径错
字段：BT-82
当前结果：少了一层 cac:Party
正确结果：/ubl:Invoice/cac:AccountingCustomerParty/cac:Party/cbc:EndpointID
怎么取：按这一行的完整层级取，不要跳父节点
```

### 场景 C：必填性/基数抽错

做法：

1. 高亮 `Mandatory`、`Optional`、`0..1`、`1..1` 之类的原文
2. 写批注：

```text
问题类型：基数错
字段：BT-24
当前结果：0..1
正确结果：1..1
怎么取：原文写的是 mandatory
```

### 场景 D：说明文字串脏

做法：

1. 高亮真正的说明段
2. 如果结果里把下一行说明、脚注、规则也并进来了，就写：

```text
问题类型：说明串脏
字段：BT-83
怎么取：描述只到本段末尾，后面的规则说明不要并进 field_description
```

## 5. 网站批注教程

网站不要直接拿线上 URL 做批注。先存证。

### 场景 A：单页字段表网站

适合：

- MyInvois 这种主页面已经有字段表的网站

做法：

1. 把页面打印成 PDF
2. 在 PDF 上按上面的 PDF 规则批注

示例：

```text
问题类型：类型错
字段：InvoiceTypeCode
当前结果：Text
正确结果：Code
怎么取：按这一列 Type，不要从 Description 猜
```

### 场景 B：drill-down 树网站

适合：

- Peppol 这种入口页只是树、详情要点进去的网站

做法：

1. 保存两份 PDF：
   - 树页
   - 详情页
2. 如果问题是“没跟详情页”，就在详情页上批注，不要只在树页上写

示例：

```text
问题类型：详情漏跟
字段：cbc:EndpointID
怎么取：树页只能拿 cardinality，description 和 example 要从这个详情页取
```

如果路径错，可以在树页上再补一条：

```text
问题类型：路径错
字段：cbc:EndpointID
怎么取：从树页的父链恢复完整 invoice_path
```

## 6. 一个完整案例

下面给一个可直接照抄的案例。

### 案例：PDF 中必填性抽错

评审动作：

1. 打开原 PDF
2. 找到字段 `BT-24`
3. 高亮原文里 `Mandatory`
4. 加批注：

```text
问题类型：基数错
字段：BT-24
当前结果：0..1
正确结果：1..1
怎么取：原文写的是 mandatory，应输出 1..1
```

我后续会据此做三件事：

1. 定位 `BT-24` 的原始证据
2. 对比当前 `field_catalog` 的 `cardinality`
3. 判断这是：
   - 单案例问题，改 overlay
   - 多国共性问题，改 family base

## 7. 建议的交付物

每个 review case 最好交这几样：

```text
review_cases/
  <case_id>/
    source.pdf
    annotated_source.pdf
    candidate.field_catalog.json
    notes.md
```

说明：

- `source.pdf`
  - 原始文件
- `annotated_source.pdf`
  - 评审后带批注的版本
- `candidate.field_catalog.json`
  - 当前 parser 输出
- `notes.md`
  - 可选。只写 case 背景，不写逐条问题

## 8. 评审人不要做的事

不要这样写：

- “这里不太对”
- “这个感觉有问题”
- “请检查一下”
- “应该按上下文理解”

这些对人有用，对机器没用。

至少要写出：

- 问题类型
- 字段或节点
- 怎么取

## 9. 最短可用版本

如果评审人时间很少，每条批注至少写成这样：

```text
问题类型：漏抽
字段：BT-146
怎么取：这一行也要出现在输出里
```

或者：

```text
问题类型：路径错
字段：cbc:EndpointID
怎么取：保留父节点 cac:Party
```

这已经够我后面消费了。
