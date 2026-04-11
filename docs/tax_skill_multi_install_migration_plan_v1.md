# Tax Skill 多可安装拆分迁移方案 v1

## 1. 目标

本文档回答一个具体实施问题：

- 如果要把当前 `tax-law-parser` 拆成多个**可安装** skill，仓库里现有文件应该怎么迁

这里的“可安装”指的是：

- 每个 skill 都可以作为一个独立目录发布
- 安装后不依赖当前仓库路径假设
- 国家包之间不互相 import

推荐目标形态不是“复制出多个大 skill”，而是：

- 一个共享 Python runtime
- 一个薄的 core skill
- 多个薄的国家 pack skill

## 2. 目标结构

```text
repo/
  python/
    tax_parser_runtime/
      __init__.py
      registry.py
      runner.py
      validator.py
      diffing.py
      testing.py
      monitoring.py
      followups.py
      families/
        en16931_ubl/
          __init__.py
          base.py

  skills/
    tax-parser-core/
      SKILL.md
      scripts/
        bootstrap_pack.py
        bootstrap_overlay.py
      references/
        parser-families.md
        overlays.md
        repair-playbook.md
      prompts/
        adapt_new_tax_law.md

    tax-pack-rs-einvoice/
      SKILL.md
      pack.json
      profiles/
        registry.json
        overlays/
          rs_overlay.py
      sources/
        official_sources.yaml
      baselines/
        rs-srbdt-ext-2025/
          field_catalog.json
          baseline_meta.json

    tax-pack-hr-einvoice/
      SKILL.md
      pack.json
      profiles/
        registry.json
        overlays/
          hr_overlay.py
      sources/
        official_sources.yaml
      baselines/
        hr-einvoice-legacy/
          field_catalog.json
          baseline_meta.json
```

## 3. 设计原则

1. `runtime` 承担所有真实可执行逻辑。
2. `core skill` 只承担 workflow、脚手架、说明和少量调度入口。
3. `pack skill` 只承担国家差异资产，不复制通用解析框架。
4. 运行脚本只依赖 `tax_parser_runtime`，不依赖别的 skill 目录。
5. 发布单元是 skill 目录；复用单元是 Python package。

## 4. 为什么必须加 runtime package

如果没有 `tax_parser_runtime`，多 skill 方案会马上遇到两个问题：

1. skill 之间没有稳定依赖管理
2. 任何一个国家 pack 都不得不复制 `run_tax_parser.py`、`validate_tax_output.py`、`compare_field_catalogs.py`

这会把“一个大 skill”变成“多个重复 skill”。

所以迁移的第一步不是拆国家目录，而是把可执行逻辑从 skill 目录抽出来。

## 5. 当前文件到目标结构的映射

### 5.1 保留在 core skill

这些文件主要是 workflow、说明或脚手架，应进入 `skills/tax-parser-core/`：

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/SKILL.md` | `skills/tax-parser-core/SKILL.md` | 重写为“core + pack”使用说明，不再直接声明国家知识 |
| `.opencode/skills/tax-law-parser/references/parser-families.md` | `skills/tax-parser-core/references/parser-families.md` | 通用文档，保留 |
| `.opencode/skills/tax-law-parser/references/overlays.md` | `skills/tax-parser-core/references/overlays.md` | 通用文档，保留 |
| `.opencode/skills/tax-law-parser/references/repair-brief.md` | `skills/tax-parser-core/references/repair-brief.md` | 通用文档，保留 |
| `.opencode/skills/tax-law-parser/references/repair-playbook.md` | `skills/tax-parser-core/references/repair-playbook.md` | 通用文档，保留 |
| `.opencode/skills/tax-law-parser/references/families/en16931-ubl.md` | `skills/tax-parser-core/references/families/en16931-ubl.md` | family 参考文档 |
| `.opencode/skills/tax-law-parser/prompts/adapt_new_tax_law.md` | `skills/tax-parser-core/prompts/adapt_new_tax_law.md` | 通用适配提示词 |
| `.opencode/skills/tax-law-parser/scripts/bootstrap_extractor.py` | `skills/tax-parser-core/scripts/bootstrap_pack.py` + `bootstrap_overlay.py` | 逻辑要拆成 pack 初始化和 overlay 初始化 |

### 5.2 抽到 runtime package

这些文件是“真实执行逻辑”，不该继续留在 skill 目录内部耦合调用，应迁到 `python/tax_parser_runtime/`：

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/skill_registry.py` | `python/tax_parser_runtime/registry.py` | 负责 profile/legacy registry 读取 |
| `.opencode/skills/tax-law-parser/runtime_python.py` | `python/tax_parser_runtime/python_exec.py` | 解释器选择逻辑 |
| `.opencode/skills/tax-law-parser/scripts/run_tax_parser.py` | `python/tax_parser_runtime/runner.py` | 主运行入口 |
| `.opencode/skills/tax-law-parser/scripts/validate_tax_output.py` | `python/tax_parser_runtime/validator.py` | 输出验证 |
| `.opencode/skills/tax-law-parser/scripts/compare_field_catalogs.py` | `python/tax_parser_runtime/diffing.py` | baseline diff |
| `.opencode/skills/tax-law-parser/scripts/test_extractor.py` | `python/tax_parser_runtime/testing.py` | compile + run + validate + compare |
| `.opencode/skills/tax-law-parser/scripts/monitor_official_sources.py` | `python/tax_parser_runtime/monitoring.py` | source 监控 |
| `.opencode/skills/tax-law-parser/scripts/run_source_followups.py` | `python/tax_parser_runtime/followups.py` | 监控后的桥接执行 |
| `.opencode/skills/tax-law-parser/scripts/promote_baseline.py` | `python/tax_parser_runtime/promote.py` | baseline 提升工具 |
| `.opencode/skills/tax-law-parser/scripts/repair_extractor_brief.py` | `python/tax_parser_runtime/repair_brief.py` | 诊断工具 |
| `.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/base.py` | `python/tax_parser_runtime/families/en16931_ubl/base.py` | family base 必须共享 |
| `.opencode/skills/tax-law-parser/schemas/tax_field_catalog.schema.json` | `python/tax_parser_runtime/schemas/tax_field_catalog.schema.json` | 统一 schema |

### 5.3 迁入 Serbia pack

这些文件带有 Serbia 特定知识，应进入 `skills/tax-pack-rs-einvoice/`：

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/rs_overlay.py` | `skills/tax-pack-rs-einvoice/profiles/overlays/rs_overlay.py` | RS overlay |
| `.opencode/skills/tax-law-parser/sources/rs/official_sources.yaml` | `skills/tax-pack-rs-einvoice/sources/official_sources.yaml` | RS 官方源 |
| `.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/field_catalog.json` | `skills/tax-pack-rs-einvoice/baselines/rs-srbdt-ext-2025/field_catalog.json` | RS baseline |
| `.opencode/skills/tax-law-parser/baselines/rs/rs-srbdt-ext-2025/baseline_meta.json` | `skills/tax-pack-rs-einvoice/baselines/rs-srbdt-ext-2025/baseline_meta.json` | RS baseline 元数据 |

Serbia pack 里的 `profiles/registry.json` 只保留 Serbia 自己的条目：

- `rs-srbdt-ext-2025`

### 5.4 迁入 Croatia pack

这些文件带有 Croatia 特定知识，应进入 `skills/tax-pack-hr-einvoice/`：

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/profiles/families/en16931_ubl/hr_overlay.py` | `skills/tax-pack-hr-einvoice/profiles/overlays/hr_overlay.py` | HR overlay |
| `.opencode/skills/tax-law-parser/sources/hr/official_sources.yaml` | `skills/tax-pack-hr-einvoice/sources/official_sources.yaml` | HR 官方源 |
| `.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/field_catalog.json` | `skills/tax-pack-hr-einvoice/baselines/hr-einvoice-legacy/field_catalog.json` | HR baseline |
| `.opencode/skills/tax-law-parser/baselines/hr/hr-einvoice-legacy/baseline_meta.json` | `skills/tax-pack-hr-einvoice/baselines/hr-einvoice-legacy/baseline_meta.json` | HR baseline 元数据 |

Croatia pack 里的 `profiles/registry.json` 只保留 Croatia 自己的条目：

- `hr-einvoice-legacy`
- `hr-ai-generated-smoke`

### 5.5 进入 legacy compatibility 区

这些文件不是优先形态，但为了兼容历史流程，可以临时收纳到 runtime 的 legacy 区：

| 当前路径 | 目标路径 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/extractors/registry.json` | `python/tax_parser_runtime/legacy/registry.json` | legacy 平铺 registry |
| `.opencode/skills/tax-law-parser/extractors/template_generic.py` | `python/tax_parser_runtime/legacy/template_generic.py` | legacy 模板 |
| `.opencode/skills/tax-law-parser/extractors/hr_ai_generated_smoke.py` | `python/tax_parser_runtime/legacy/hr_ai_generated_smoke.py` | 历史兼容 |
| `.opencode/skills/tax-law-parser/extractors/hr_einvoice_legacy.py` | `python/tax_parser_runtime/legacy/hr_einvoice_legacy.py` | 历史兼容 |
| `.opencode/skills/tax-law-parser/extractors/rs_srbdt_ext_2025.py` | `python/tax_parser_runtime/legacy/rs_srbdt_ext_2025.py` | 仅作兼容，不作为未来主路线 |

### 5.6 不应迁入 published skill

这些内容不应作为发布物的一部分：

| 当前路径 | 处理方式 | 说明 |
| --- | --- | --- |
| `.opencode/skills/tax-law-parser/__pycache__/...` | 删除 | 构建产物 |
| `.opencode/skills/tax-law-parser/scripts/__pycache__/...` | 删除 | 构建产物 |
| `.opencode/skills/tax-law-parser/extractors/__pycache__/...` | 删除 | 构建产物 |
| `.opencode/skills/tax-law-parser/profiles/__pycache__/...` | 删除 | 构建产物 |
| `.opencode/skills/tax-law-parser/sources/README.md` | 不进 published skill | 供当前仓库开发参考，可移到 docs |
| `.opencode/skills/tax-law-parser/sources/index.yaml` | 删除或改成上层 catalog | 多 skill 后不再需要单 skill 汇总入口 |

## 6. 迁移后的入口设计

### 6.1 runtime CLI

未来的真实执行入口应统一变成：

```bash
python -m tax_parser_runtime.runner \
  --pack-dir <pack_dir> \
  --pdf <pdf_path> \
  --outdir <outdir>
```

测试入口：

```bash
python -m tax_parser_runtime.testing \
  --pack-dir <pack_dir> \
  --pdf <pdf_path> \
  --extractor <profile_name> \
  --outdir <outdir>
```

监控入口：

```bash
python -m tax_parser_runtime.monitoring \
  --pack-dir <pack_dir> \
  --outdir <outdir>
```

这样每个国家 pack 只需要把自己的 `pack_dir` 传进去。

### 6.2 pack skill 的对外命令

每个 pack skill 保留一个很薄的 wrapper 脚本即可，例如 Serbia：

```bash
python scripts/run_pack.py \
  --pdf <pdf_path> \
  --outdir <outdir>
```

这个 wrapper 内部只做一件事：

- 把 `--pack-dir` 固定为当前 skill 目录
- 调 `python -m tax_parser_runtime.runner`

## 7. 每个 pack skill 的最小文件合同

每个 pack 至少包含：

### 7.1 `SKILL.md`

只描述：

- 这个 pack 适用于哪个国家和税种
- 默认入口 profile 是什么
- 何时需要更新 source、overlay、baseline

不重复解释 runtime 细节。

### 7.2 `pack.json`

建议结构：

```json
{
  "pack_name": "tax-pack-rs-einvoice",
  "jurisdiction": "RS",
  "tax_domain": "einvoice",
  "entry_profile": "rs-srbdt-ext-2025",
  "default_family": "en16931_ubl",
  "runtime_package": "tax_parser_runtime"
}
```

### 7.3 `profiles/registry.json`

只允许本 pack 的 profile 条目，不允许跨国家。

### 7.4 `sources/official_sources.yaml`

只允许本 pack 的官方源，不允许混合别国数据。

## 8. 分阶段迁移顺序

### 阶段 1：抽 runtime

先做这些，不拆 skill：

1. 新建 `python/tax_parser_runtime/`
2. 把 `run_tax_parser.py`、`validate_tax_output.py`、`compare_field_catalogs.py`、`test_extractor.py` 等逻辑迁进去
3. 保留当前 skill 下的脚本作为 shim，内部转调 runtime

验收标准：

- 当前 `tax-law-parser` skill 行为不变
- 现有 HR/RS profile 全部还能跑

### 阶段 2：建第一个 pack

优先建 `tax-pack-rs-einvoice`：

1. 新建 `skills/tax-pack-rs-einvoice/`
2. 搬 `rs_overlay.py`
3. 搬 RS baseline
4. 搬 RS source registry
5. 加 `pack.json`
6. 用 runtime 跑一次 Serbia 全链路

验收标准：

- 不依赖 `.opencode/skills/tax-law-parser/`
- `monitoring -> followups -> testing` 能独立跑通

### 阶段 3：建第二个 pack

复制 Serbia 模式到 Croatia：

1. 新建 `skills/tax-pack-hr-einvoice/`
2. 搬 `hr_overlay.py`
3. 搬 HR baseline
4. 搬 HR source registry
5. 跑 Croatia 质量门

验收标准：

- Croatia pack 可以独立运行
- 与 Serbia pack 没有跨目录 import

### 阶段 4：收缩 core

最后处理 `tax-parser-core`：

1. 重写 `SKILL.md`
2. 保留 references、prompts、bootstrap 工具
3. 删除国家特定 profile 和 baseline

验收标准：

- core skill 不再携带 RS/HR 特定资产
- core skill 可以指导 agent 创建新的 pack

## 9. 发布方式

最终发布时，每个 skill 目录单独安装：

```bash
scripts/install-skill-from-github.py \
  --repo your-org/tax-skills \
  --path skills/tax-parser-core \
  --path skills/tax-pack-rs-einvoice \
  --path skills/tax-pack-hr-einvoice
```

注意：

- `tax_parser_runtime` 不是 skill，要作为 Python package 发布或随仓库安装
- 否则 skill 装好了也跑不起来

## 10. 最小可执行路线

如果只做一件最有价值的事，优先顺序应是：

1. 先抽 `tax_parser_runtime`
2. 先做 `tax-pack-rs-einvoice`
3. 验证独立安装可跑
4. 再复制到 Croatia

这条路线的好处是：

- 改动面最小
- 最快验证“多可安装 skill”不是纸面设计
- Serbia 当前 source monitor 和 follow-up 已经较完整，最适合作为第一个 pack
