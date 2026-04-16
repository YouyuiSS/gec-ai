# AGENTS

给接手这个仓库的 AI 开发者看的执行版说明。不是用户文档。

## 目标

- 输入是 PDF 或规范网址。
- 先判断 `family`，再解析成统一 `field_catalog`。
- 复用单位是 `family`，不是国家。
- 国家差异放 `pack`，解析共性放 `family`。

## 先看

1. `docs/README.md`
2. `docs/tax_family_program_v1.md`
3. `docs/tax_skill_workbench_architecture_v1.md`

## 先按 harness 来

先记住：这个项目不是“直接改 parser”，而是“先过护栏，再开发，最后过 gate”。

### 1. 改之前先跑 `security_guard.py`

默认先检查计划修改的文件：

```bash
python scripts/harness/security_guard.py --path <file1> --path <file2>
```

规则：

- 默认允许：
  - `.opencode/skills/tax-law-parser/`
  - `docs/`
  - `AGENTS.md`
- 默认不允许：
  - `profiles/families/*/base.py`
  - `baselines/`
  - 其他仓库路径

只有明确需要时，才带：

```bash
--allow-family-base-writes
--allow-baseline-writes
```

### 2. 做完后用 `quality_gate.py` 收口

如果输入是 PDF，尽量跑：

```bash
python scripts/harness/quality_gate.py \
  --pdf <pdf_path> \
  --extractor <name> \
  --outdir <outdir>
```

当前限制：

- `quality_gate.py` 还是 PDF 导向
- web 目前主要靠 `test_extractor.py` 验证

不要把“parser 能跑”当成“已经过 gate”。

## 目录职责

- `.opencode/skills/tax-law-parser/`
  - 主开发面。新 `family`、runtime、overlay、registry 先在这里做。
- `skills/`
  - 发布面。只有内部验证通过后才同步。
- `scripts/harness/`
  - 护栏和 gate。
- `tax_pipeline/`
  - 下游流水线，不是前台 parser runtime。

## 当前 family

- `pdf_field_dictionary`
- `pdf_xsd_spec`
- `web_inline_table`
- `web_drilldown_tree`

## 怎么判断该改哪层

按这个顺序判断：

1. 先看 `source kind`
   - `PDF` / `web` / `other`
   - 如果输入类型都变了，先补 source/runtime，不要先建国家包。
2. 再看 `family shape`
   - 能落进现有 family，就不要新建 family。
3. 现有 family 内的改动优先级
   - 路由或 hint 错：改 `profiles/registry.json`
   - 单国差异：改 `profiles/families/<family>/*_overlay.py`
   - 多国共性：改 `tax_parser_runtime/families/<family>/base.py`
4. 只有在解析机制本质不同、而且后续可复用时，才新建 family。

不要因为这些原因新建 family：

- 文档语言不同
- 表头小改
- 路径命名略有差异
- 某个国家页面轻微改版

## 开发顺序

1. 先用 `security_guard.py` 确认改动范围。
2. 先在 `.opencode` 内实现，不要先改 `skills/` 发布面。
3. 优先顺序：
   - `profiles/registry.json`
   - `profiles/families/<family>/*_overlay.py`
   - `tax_parser_runtime/families/<family>/base.py`
   - `runner.py` 或 source plumbing
4. 跑：
   - `python -m py_compile <changed_python_files>`
5. 再跑：
   - `.venv/bin/python .opencode/skills/tax-law-parser/scripts/test_extractor.py --source <pdf_or_url> --extractor <name> --outdir <outdir>`
6. 如果是 PDF，尽量再跑：
   - `python scripts/harness/quality_gate.py --pdf <pdf_path> --extractor <name> --outdir <outdir>`
7. 确认支持范围后，再决定是否同步到 `skills/`。

## Web 规则

- `web_inline_table`
  - 主页面字段表就是主数据源，外链只做补充。
- `web_drilldown_tree`
  - 树页只是入口，必须继续跟子链接抓详情。

不要因为页面里有 `<table>`，就把 drill-down 站点误判成 inline table。

## 汇报要求

每次完成 parser 任务，至少说明：

1. 测了什么 source
2. 用了哪个 extractor/profile
3. 属于哪个 family
4. 是显式命中还是自动匹配
5. 记录数
6. validator 是否通过
7. quality gate 是否通过
8. 只是 `.opencode` 内部支持，还是已经同步到 `skills/`

不要把“内部可跑”说成“对外已支持”。
