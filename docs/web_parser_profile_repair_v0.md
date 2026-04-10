# Web Parser Profile Repair v0

## 背景

当前项目已经有两套相关能力，但职责不同：

- 本地 `.opencode` skill 用于开发期调试和人工适配 PDF
- `tax_pipeline` + `tax_ui` 是服务端和 web 侧实际运行的解析链路

本方案只讨论 web 应用侧的在线修复能力，不依赖本地 skill，也不要求在线环境能改 Python 代码。

目标是把一部分易漂移、可参数化的解析规则外置成数据库里的版本化元数据。当抽取结果有问题时，用户在 web 端反馈问题，AI 只生成受限的 metadata patch，服务端校验后重跑解析，再由人工决定是否采纳。

## 核心原则

1. 代码是稳定引擎，元数据是可调参数
   AI 不改服务端代码，只改白名单内的 parser metadata。

2. 版本化而不是覆盖
   任何 AI 调整都生成新的 profile version，不直接覆盖当前 active 版本。

3. 单问题、单类型、少量 patch
   每次 repair 只处理一个具体问题，AI 只允许返回 1 到 3 条结构化 patch。

4. 先重跑，再采纳
   新 metadata 必须经过重跑和对比，不能直接生效。

5. 超出元数据边界时显式失败
   如果问题需要新增解析算法或改代码，AI 必须返回 `needs_engine_change`，而不是硬修。

## 目标

- 支持 web 侧对解析错误进行最小闭环修复
- 将高频、低风险的解析 heuristics 外置到数据库
- 让 AI 只调窄范围的元数据，不接触服务端代码
- 为每次解析和每次修复保留可审计的版本与运行记录

## 非目标

- 不做“AI 自动维护整套 parser”
- 不做任意 JSON 元数据编辑器
- 不在 v0 支持任意 plugin 式自定义 repair
- 不替代现有 deterministic extractor 的主体代码

## v0 范围

v0 只开放 4 类元数据：

1. `header_aliases`
   表头别名到 canonical key 的映射

2. `path_replace_rules`
   在路径切分前做的字符串替换规则

3. `block_scores`
   `detail_block` / `table_block` 候选打分权重

4. `constraint_rules`
   长度、精度、格式提示的正则推断规则

这 4 类对应当前代码里最容易漂移且最适合参数化的区域，主要来自 [`scripts/extract_tax_fields.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/scripts/extract_tax_fields.py)。

## 总体架构

### 运行态

1. web 端发起正常解析
2. 服务端为本次 run 加载当前 active 的 `parser_profile_version`
3. deterministic extractor 按代码框架执行，但其中的可配置点从 `metadata_json` 读取
4. 生成 bundle、validation、diff、review artifacts

### 修复态

1. 用户在 web 端标记某个字段或某类解析问题
2. 服务端创建 repair ticket，并收集：
   - 当前 profile version
   - 当前抽取值
   - 用户期望值
   - evidence excerpt
   - validation / diff 摘要
3. 服务端按 `issue_type` 组装一个最小 repair request 发给 AI
4. AI 返回受限 patch
5. 服务端做 schema 校验和白名单校验
6. 服务端落一条新的 `parser_profile_version`
7. 使用新的 candidate version 重跑同一 PDF
8. 展示 before / after、validation 变化、目标字段变化
9. 人工确认后，切换该 version 为 active

## 元数据模型

v0 元数据放在 `parser_profile_version.metadata_json` 中。

参考 Schema：

- [`schemas/parser_profile_metadata.schema.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/schemas/parser_profile_metadata.schema.json)

### 结构

```json
{
  "schema_version": "1.0",
  "header_aliases": {
    "ID": "field_id",
    "Business term": "field_name"
  },
  "path_replace_rules": [
    { "from": "/invoice/", "to": "/Invoice/" }
  ],
  "block_scores": {
    "detail": {
      "contains:Business Rule": 3,
      "contains:Example of use:": 2
    },
    "table": {
      "line_startswith_path": 5,
      "contains:Business Rule": -2
    }
  },
  "constraint_rules": [
    {
      "name": "time-format",
      "regex": "format\\s+hh:mm:ss",
      "set_if_empty": {
        "min_char_length": "8",
        "max_char_length": "8"
      }
    }
  ]
}
```

### 设计约束

- `schema_version` 固定为 `1.0`
- 顶层字段固定，禁止自由扩展
- `header_aliases` 的 value 只能映射到预定义 canonical key
- `path_replace_rules` 为有序数组，先后顺序有意义
- `block_scores` 的 key 必须是引擎识别的 signal name
- `constraint_rules` 只允许 `set` 或 `set_if_empty` 两种赋值方式

## 数据库设计

v0 新增 3 张表，并给现有 `extraction_run` 增加一个关联字段。

参考 SQL 草案：

- [`sql/parser_profile_v0.sql`](/Users/xueyunsong/Documents/GitHub/gec-ai/sql/parser_profile_v0.sql)

### `parser_profile`

表示一组稳定的解析 profile 身份：

- `jurisdiction`
- `tax_domain`
- `document_family`
- `language_code`
- `active_version_id`

这一层不存大 JSON，只解决“当前应该用哪组 profile”。

### `parser_profile_version`

表示 profile 的版本化元数据：

- `version_no`
- `schema_version`
- `metadata_json`
- `source`，取值 `human` / `ai`
- `change_summary`
- `created_by`

这一层存完整 metadata，并允许多版本并存。

### `parser_repair_ticket`

表示一次 web 侧 repair 闭环：

- 当前 run
- 当前使用的 profile version
- 字段编码或问题类型
- 用户反馈
- AI 请求和响应
- patch
- 重跑摘要
- 最终状态

## AI 输入输出协议

v0 不允许 AI 返回整份 metadata，只允许返回受限操作。

### 支持的操作

- `add_header_alias`
- `add_path_replace_rule`
- `update_block_score`
- `add_constraint_rule`

v0 不支持删除操作，也不支持任意 JSON Patch。

### 修复请求

请求只包含当前问题相关的最小上下文：

- `issue_type`
- `field_code`
- `current_value`
- `expected_value`
- `feedback_text`
- `evidence`
- `current_metadata_subset`
- `allowed_operations`

### 修复响应

响应包含：

- `issue_type`
- `operations`
- `reason`

如果问题超出元数据边界，AI 返回：

- `issue_type = needs_engine_change`
- 简短原因

## 服务端校验

在写入新的 `parser_profile_version` 前，服务端必须执行以下校验：

1. JSON Schema 校验
   新的 `metadata_json` 必须符合 [`schemas/parser_profile_metadata.schema.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/schemas/parser_profile_metadata.schema.json)。

2. Patch 白名单校验
   AI 只能使用请求中开放的操作。

3. 值域校验
   - score 范围受限
   - regex 长度受限
   - replace rule 数量受限
   - canonical key 必须合法

4. 幂等和去重
   如果 patch 不产生实际变化，不创建新 version。

## 运行与采纳策略

### 版本流转

1. 当前 active profile version 参与生产解析
2. AI 生成 patch
3. 服务端创建新的 candidate profile version
4. candidate version 只用于 repair rerun
5. 人工确认后，更新 `parser_profile.active_version_id`

### 结果判断

v0 的“建议采纳”逻辑只看以下信号：

- 目标字段是否变成期望值
- validation issue 是否减少
- 没有新增高风险错误

如果目标字段未改善，或引入更多错误，repair ticket 标记为 `rerun_failed`。

## 接口建议

v0 建议提供以下接口：

### `POST /api/parser-repairs`

创建 repair ticket。

请求体建议包含：

- `run_id`
- `field_code`
- `issue_type`
- `feedback_text`
- `expected_value`

### `GET /api/parser-repairs/{ticket_id}`

查看 repair ticket 详情，包括：

- AI patch
- candidate profile version
- rerun summary
- before / after 差异

### `POST /api/parser-repairs/{ticket_id}/apply`

将 candidate profile version 提升为 active version。

### `GET /api/parser-profiles/{profile_id}/versions`

查看某个 profile 的版本历史，支持回滚。

## 风险与边界

### 适合元数据修复的问题

- 表头别名变化
- path 大小写或局部命名差异
- block 识别权重不合适
- 文档明确写了格式或精度，但规则未覆盖

### 不适合元数据修复的问题

- PDF 表格结构完全变化
- OCR 噪声严重
- 需要新增新的块分割算法
- 需要新的 special-case 代码逻辑

这些情况应直接输出 `needs_engine_change`。

## 实施顺序

### Phase 1

- 建表并引入 `parser_profile_version`
- 在 extractor 中接入 `metadata_json`
- 将现有 4 类硬编码逻辑改为读 metadata

### Phase 2

- 增加 repair ticket API
- 增加 AI repair workflow
- 增加 rerun 对比和“建议采纳”判定

### Phase 3

- 增加 profile version 历史和回滚 UI
- 增加常见问题的 repair 模板
- 视效果决定是否扩展元数据面

## 当前产物

本方案对应的初始草案已经落库到仓库：

- 文档：[`docs/web_parser_profile_repair_v0.md`](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/web_parser_profile_repair_v0.md)
- Schema：[`schemas/parser_profile_metadata.schema.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/schemas/parser_profile_metadata.schema.json)
- SQL：[`sql/parser_profile_v0.sql`](/Users/xueyunsong/Documents/GitHub/gec-ai/sql/parser_profile_v0.sql)

后续如果进入实现阶段，下一步应先补：

1. repair patch 的请求/响应 schema
2. extractor 对 `metadata_json` 的读取适配
3. web repair API 与 rerun 闭环
