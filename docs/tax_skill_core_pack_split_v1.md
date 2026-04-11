# Tax Skill Core + Pack 拆分方案 v1

## 1. 文档目的

本文档回答一个更具体的问题：

- 如果未来希望 tax skill 具备一定的“自迭代”能力，当前工程应该继续维持一个大 skill，还是拆成多个更小的 skill

这里的结论不是简单的：

- 一个国家一个完全独立 skill

而是：

- **一个稳定的 core skill**
- **多个薄的 pack skill**

也就是：

- `core` 负责稳定引擎、路由协议、执行脚本、校验、diff、repair brief
- `pack` 负责国家或文档族的来源、profile、baseline、fixture、少量 override

## 2. 为什么这比“一个大 skill”更适合自迭代

当前仓库已经从 flat extractor 演进到了：

- `profiles/families/.../base.py`
- `profiles/families/.../*_overlay.py`

这说明工程已经接受了一个事实：

- 共性应该收敛
- 差异应该隔离

如果下一步还把所有国家资产继续塞在同一个 skill 里，问题会变成：

1. skill 上下文越来越大
2. agent 修改时很难确认自己会不会影响别的国家
3. baseline、fixture、sources 会越来越分散
4. “引擎缺陷”和“国家资料漂移”会继续耦合

而自迭代最怕的就是写入面过大。

所以，如果把自迭代作为显式目标，最合理的边界就是：

- core skill 尽量少改
- pack skill 高频小改

## 3. 设计结论

### 3.1 推荐形态

推荐采用：

- 一个 `tax-parser-core` skill
- 多个 `tax-pack-*` skill

推荐命名示例：

- `.opencode/skills/tax-parser-core`
- `.opencode/skills/tax-pack-hr-einvoice`
- `.opencode/skills/tax-pack-rs-einvoice`
- `.opencode/skills/tax-pack-peppol-pint`

### 3.2 核心原则

1. `core` 不存国家特定知识
2. `pack` 不复制通用解析框架
3. `pack` 优先放 metadata / overlay / baseline，只有必要时才放 Python override
4. 用户入口可以仍然是一个主 skill，但物理存储应拆开
5. 自迭代默认只允许改当前命中的 pack；只有显式 `needs_engine_change` 才允许改 core

## 4. skill 拆分边界

### 4.1 core skill 负责什么

`tax-parser-core` 负责：

- 文档匹配和路由协议
- 统一输出合同
- 统一运行脚本
- 统一 validate / compare / repair brief
- family parser base
- legacy 兼容层
- baseline 提升工具
- 发现 `needs_engine_change`

换句话说，core 负责的是：

- how to parse
- how to test
- how to diff
- how to diagnose

它不负责：

- which country source to watch
- which baseline is trusted for Serbia
- Croatia 的 header alias 是什么

### 4.2 pack skill 负责什么

`tax-pack-*` 负责：

- 官方来源列表
- 国家/税种/document family 的 profile 注册
- baseline
- fixture PDF
- parser metadata
- 极少量 override 代码
- 该国家的 notes / playbook

换句话说，pack 负责的是：

- what to monitor
- what to parse for this domain
- what good output looks like

## 5. 推荐目录结构

### 5.1 core skill

```text
.opencode/skills/tax-parser-core/
  SKILL.md
  skill_router.py
  references/
    workflow.md
    canonical-model.md
    parser-families.md
    repair-brief.md
    families/
      en16931-ubl.md
      peppol-pint.md
      schema-first.md
  scripts/
    run_parser.py
    validate_catalog.py
    compare_catalogs.py
    test_profile.py
    build_repair_brief.py
    promote_baseline.py
    bootstrap_pack.py
    bootstrap_overlay.py
  families/
    en16931_ubl/
      __init__.py
      base.py
    peppol_pint/
      __init__.py
      base.py
    schema_first/
      __init__.py
      base.py
  legacy/
    extractors/
      __init__.py
      registry.json
      template_generic.py
  schemas/
    tax_field_catalog.schema.json
```

### 5.2 pack skill

以 Serbia eInvoice 为例：

```text
.opencode/skills/tax-pack-rs-einvoice/
  SKILL.md
  pack.json
  sources/
    official_sources.yaml
  profiles/
    registry.json
    rs_srbdt_ext_2025.json
  overlays/
    rs_overlay.py
  baselines/
    rs-srbdt-ext-2025/
      field_catalog.json
      baseline_meta.json
  fixtures/
    smoke/
      sample.pdf
  references/
    source-notes.md
    review-playbook.md
```

Croatia pack 类似：

```text
.opencode/skills/tax-pack-hr-einvoice/
  SKILL.md
  pack.json
  sources/
    official_sources.yaml
  profiles/
    registry.json
    hr_einvoice_legacy.json
  overlays/
    hr_overlay.py
  baselines/
    hr-einvoice-legacy/
      field_catalog.json
      baseline_meta.json
  fixtures/
  references/
```

## 6. pack skill 的最小合同

每个 pack skill 至少应提供：

### 6.1 `pack.json`

推荐字段：

```json
{
  "pack_name": "tax-pack-rs-einvoice",
  "jurisdiction": "RS",
  "tax_domain": "einvoice",
  "default_family": "en16931_ubl",
  "entry_profile": "rs-srbdt-ext-2025",
  "core_skill": "tax-parser-core"
}
```

### 6.2 `sources/official_sources.yaml`

推荐字段：

- `source_name`
- `kind`
- `landing_url`
- `download_url`
- `discovery_method`
- `expected_language`
- `document_family`
- `check_interval`
- `notes`

### 6.3 `profiles/registry.json`

每条 profile 至少包含：

- `name`
- `family`
- `module` 或 `profile_path`
- `jurisdiction`
- `tax_domain`
- `document_language`
- `filename_contains`
- `text_contains`
- `baseline_path`

## 7. 当前仓库文件映射

下面是当前仓库到 `core + pack` 的建议映射。

### 7.1 进入 core 的文件

当前这些文件应归到 `tax-parser-core`：

- [`.opencode/skills/tax-law-parser/scripts/run_tax_parser.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/run_tax_parser.py)
- [`.opencode/skills/tax-law-parser/scripts/validate_tax_output.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/validate_tax_output.py)
- [`.opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py)
- [`.opencode/skills/tax-law-parser/scripts/test_extractor.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/test_extractor.py)
- [`.opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py)
- [`.opencode/skills/tax-law-parser/scripts/promote_baseline.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/scripts/promote_baseline.py)
- [`.opencode/skills/tax-law-parser/skill_registry.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/skill_registry.py)
- [`.opencode/skills/tax-law-parser/schemas/tax_field_catalog.schema.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/schemas/tax_field_catalog.schema.json)
- [`.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/base.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/base.py)
- [`.opencode/skills/tax-law-parser/references/parser-families.md`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/references/parser-families.md)
- [`.opencode/skills/tax-law-parser/references/repair-brief.md`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/references/repair-brief.md)

legacy 兼容层也应先跟着 core 走：

- [`.opencode/skills/tax-law-parser/extractors/registry.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/extractors/registry.json)
- [`.opencode/skills/tax-law-parser/extractors/template_generic.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/extractors/template_generic.py)
- [`.opencode/skills/tax-law-parser/extractors/hr_ai_generated_smoke.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/extractors/hr_ai_generated_smoke.py)

### 7.2 进入 Serbia pack 的文件

建议进入 `tax-pack-rs-einvoice`：

- [`.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/rs_overlay.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/rs_overlay.py)
- [`.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/field_catalog.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/field_catalog.json)
- [`.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/baseline_meta.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/baseline_meta.json)

同时新增但当前仓库还没有的内容：

- `sources/official_sources.yaml`
- Serbia 专用 `profiles/registry.json`
- Serbia 的 source notes

### 7.3 进入 Croatia pack 的文件

建议进入 `tax-pack-hr-einvoice`：

- [`.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/hr_overlay.py`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/hr_overlay.py)
- [`.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/field_catalog.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/field_catalog.json)
- [`.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/baseline_meta.json`](/Users/xueyunsong/Documents/GitHub/gec-ai/.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/baseline_meta.json)

## 8. 路由方式

### 8.1 推荐不是“用户选 skill”

虽然物理上拆成多个 skill，但推荐仍然保留一个主入口。

也就是说：

- 用户对话里仍然主要说 `tax-parser-core`
- core 根据输入文档和 registry 决定命中哪个 pack

因为如果让用户手动选：

- `tax-pack-rs-einvoice`
- `tax-pack-hr-einvoice`
- `tax-pack-peppol-pint`

那么用户仍然要先理解工程分层，这没有必要。

### 8.2 core 的路由输入

core 需要综合：

- pack registry
- filename hint
- text hint
- source landing page
- jurisdiction / tax_domain

输出：

- `selected_pack`
- `selected_family`
- `selected_profile`
- `baseline_path`

## 9. 自迭代边界

### 9.1 默认允许 pack 自改

pack skill 可以自改：

- `sources/official_sources.yaml`
- `profiles/*.json`
- `baselines/*`
- `references/*`
- `overlays/*.py`

这是因为这些修改的 blast radius 小。

### 9.2 默认禁止 core 自改

core skill 默认不应自动改：

- `families/*/base.py`
- validate / compare / brief 主脚本
- canonical schema
- 路由协议

只有当 pack 返回：

- `needs_engine_change`

或者 repair brief 明确表明是引擎缺陷时，才允许升级到 core 修改。

### 9.3 这套边界为什么重要

因为它天然把失败分成两类：

1. `pack drift`
   资料来源变了、表头变了、局部 path 变了、baseline 过期了

2. `engine defect`
   当前 family parser 根本不能表达这个结构

这对自迭代非常关键。没有这个边界，agent 最终会把所有问题都修进核心引擎里。

## 10. 与现有 family + overlay 方案的关系

当前仓库里已经有：

- family base
- overlay
- baselines
- profile registry

所以 `core + pack` 不是推翻现有设计，而是把现有分层继续向前推一步：

- 从“一个 skill 内部分层”
- 变成“多个 skill 物理拆分”

这一步的核心收益不是抽象优雅，而是：

- 更小的写入面
- 更清晰的 ownership
- 更可控的自迭代

## 11. 建议迁移顺序

### 第一步

先不移动代码，只新增一份逻辑视图：

- 把当前文件按 `core / hr pack / rs pack` 做清单化管理

### 第二步

把来源监控资产先拆出去：

- `sources/official_sources.yaml`

因为这部分最国家化，也最适合先独立。

### 第三步

把 baseline 和 overlay 按国家迁到 pack。

### 第四步

最后再把脚本和 family base 提到 `tax-parser-core`。

## 12. 最终建议

如果你的目标只是“手动维护能跑”，一个 skill 也能继续用。

但如果你的目标包含：

- 自动发现来源变化
- 自动修 profile / overlay
- 限制自迭代改动范围
- 随国家数增长仍保持可控

那更推荐采用：

- **一个 core skill**
- **多个 pack skill**

其中：

- core 追求稳定
- pack 追求小而可改

这比“一个大 skill”更适合你当前想走的方向。
