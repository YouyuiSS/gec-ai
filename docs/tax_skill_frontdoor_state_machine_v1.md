# Tax Skill 单入口状态机方案 v1

## 1. 文档目的

本文档回答一个产品层问题：

- 用户不会主动说“怎么接一个新国家”
- 用户也不会主动说“怎么把本地改动回传 GitHub”
- 用户只会说“上传 PDF，解析税法”

所以当前 tax skill 的正确形态不应该是多个并列用户入口，而应该是：

- 一个前台主入口
- 多个后台状态驱动工作流

本文档定义这个单入口状态机。

## 2. 核心结论

用户入口应该只有一个：

- `tax-law-parser`

用户只表达业务目标：

- 解析税法 PDF

系统内部再根据运行状态自动进入不同后台流程：

- 正常解析
- 新国家接入
- 已知国家 repair
- 本地修复 publish-back

也就是说：

- `tax-pack-onboarding` 不应该依赖用户显式提问触发
- `tax-pack-publish-back` 也不应该依赖用户显式提问触发

它们更适合做后台维护工作流。

## 3. 单入口结构

### 3.1 前台入口

前台只保留一个用户可理解入口：

- `tax-law-parser`

它的职责是：

- 接收 PDF
- 尝试现有 pack/profile 解析
- 判断当前运行状态
- 根据状态切后台工作流

### 3.2 后台工作流

后台工作流可以继续存在，但定位改变：

- `tax-pack-onboarding`
  新国家或新文档族接入流程
- `tax-pack-publish-back`
  本地修复回传主库流程
- `repair workflow`
  已知 pack/profile 漂移修复流程

这些都不应要求最终用户自己命名和触发。

## 4. 状态机

### 4.1 状态图

```text
用户上传 PDF
  -> attempt_parse

attempt_parse
  -> parse_success
  -> parse_no_match
  -> parse_drift_detected

parse_no_match
  -> onboarding_flow

parse_drift_detected
  -> repair_flow

repair_flow
  -> local_fix_validated
  -> repair_failed

local_fix_validated
  -> publish_back_pending
  -> return_local_result
```

### 4.2 状态定义

#### A. `attempt_parse`

默认入口状态。

动作：

1. 读取已安装 pack 或本地可用 pack
2. 尝试自动匹配 profile
3. 运行 parser
4. 如果可用，执行 baseline compare 和 quality gate

#### B. `parse_success`

条件：

- 找到可用 profile
- parser run 成功
- 输出通过基本验证
- 若 profile 为 stable，则 gate 通过

动作：

- 返回结果给用户
- 不暴露后台维护逻辑

#### C. `parse_no_match`

条件：

- 当前没有任何 profile 能匹配 PDF

动作：

- 自动进入 `onboarding_flow`
- 判断是否属于现有 family
- 若是，则新增 pack / overlay
- 若否，则评估是否需要新增 family parser

#### D. `parse_drift_detected`

条件：

- 能匹配到已知 profile
- 但结果明显漂移、compare 超阈值、或 gate fail

动作：

- 自动进入 `repair_flow`
- 优先修改当前 pack 的 overlay / registry
- 只有跨国家共性问题才允许进入 `core`

#### E. `local_fix_validated`

条件：

- 本地修复后重新跑通 `test`
- 质量门通过

动作：

- 若当前环境可写 repo clone，则进入 `publish_back_pending`
- 否则返回本地修复结果，并提示仍需回传主库

#### F. `publish_back_pending`

条件：

- 本地修复已经通过验证
- 需要把修改回传 GitHub 主库

动作：

- 进入 publish-back 流程
- 回放改动到 repo clone
- commit / push / draft PR

## 5. 触发原则

### 5.1 用户触发

用户只触发这一件事：

- “解析这份税法 PDF”

### 5.2 系统触发

后台工作流由系统状态触发，而不是由用户提问内容触发：

- `parse_no_match` -> onboarding
- `parse_drift_detected` -> repair
- `local_fix_validated` -> publish-back

## 6. 当前 skill 结构应该如何理解

### 6.1 用户可见主 skill

应该只有一个主 skill：

- `tax-law-parser`

### 6.2 后台维护 skill

可以继续保留：

- `tax-pack-onboarding`
- `tax-pack-publish-back`

但它们更适合被看作维护工作流 skill，而不是终端用户入口。

## 7. 为什么这比“多个 skill 并列入口”更对

因为最终用户只理解业务目标，不理解工程状态。

用户不会自然知道：

- 当前是不是新国家接入
- 当前是不是 profile 漂移
- 当前是不是应该 publish-back

这些都应该由系统根据运行证据自己判断，而不是把工程分支决策外包给用户。

## 8. 推荐落地方式

### 8.1 入口层

把 `tax-law-parser` 明确定位为前台单入口 skill。

它要写清楚：

- 默认先尝试现有 pack/profile
- 不要要求用户显式提出 onboarding / publish-back
- 根据运行状态自动切后台流程

### 8.2 工作流层

保留后台 skill：

- `tax-pack-onboarding`
- `tax-pack-publish-back`

但在主入口 skill 里把它们定义为内部状态分流后的工作流，而不是用户手动选择项。

## 9. 当前推荐理解

一句话概括：

> 用户只有一个入口：上传 PDF 解析税法；系统内部根据解析状态自动进入 onboarding、repair 或 publish-back。
