# Tax Skill Publish-Back 架构方案 v1

## 1. 文档目的

本文档回答一个当前工作台里的关键问题：

- skill 安装到用户本地后，用户可能会根据最新税法手工修本地 pack
- 但 GitHub 主库不会自动感知这些本地修改
- 那么应该如何把“本地修复”安全地回传到主库

本文档的目标不是让安装目录自动双向同步，而是定义一个清晰的 `publish-back` 模型。

## 2. 核心结论

安装到用户本地的 skill 目录不是 source of truth。

推荐采用双通道模型：

1. GitHub 主库自己跑官方源监控，独立发现税法变化
2. 用户本地如果做了修复，通过一个明确的 `publish-back` 流程把改动回传到 GitHub

也就是说：

- GitHub 主库负责持续发现变化
- 本地安装 skill 负责运行和局部修复
- `publish-back` 负责把经过验证的本地修复变成 PR 或 patch

## 3. 为什么不能把安装目录当主库

如果直接把：

- `~/.codex/skills/tax-pack-...`

当作主编辑目录，会有几个问题：

1. 安装目录缺少 git 历史
2. 无法知道该改动基于哪个远端提交
3. 无法区分“本地临时试验”和“应该发布回主库的修复”
4. 多个用户各自修改后无法合流
5. GitHub 无法主动感知法规变化

所以安装目录只能视为运行副本，而不是主开发副本。

## 4. 推荐目标模型

### 4.1 三类目录

推荐把目录角色分开：

#### A. Installed Skill

位置示例：

- `~/.codex/skills/tax-parser-core`
- `~/.codex/skills/tax-pack-rs-einvoice`

作用：

- 给用户直接运行
- 不作为长期主编辑目录

#### B. Editable Repo Clone

位置示例：

- `~/work/gec-ai`

作用：

- 真正的 source-controlled 工作副本
- 负责提交、推送、开 PR

#### C. Optional Local Override Workspace

位置示例：

- `~/work/tax-pack-overrides/tax-pack-rs-einvoice`

作用：

- 在用户不想直接改 repo clone 时，先做临时修复
- 后续再导出 patch 或同步回 repo clone

### 4.2 Source of Truth

只有 GitHub repo 是 source of truth。

本地安装 skill 和 override workspace 都不是最终真相，只是运行或修改中间态。

## 5. 双通道模型

### 5.1 通道 A: Central Monitor

GitHub 主库自己跑定时监控：

1. 定时执行 pack 的 `monitor`
2. 发现 `change_report` / `review_items` / `followups`
3. 触发：
   - 自动 rerun
   - 或生成 draft PR / issue / review task

这一条链路不依赖任何用户本地动作。

### 5.2 通道 B: Local Publish-Back

用户本地修好 pack 后，不是直接留在 `~/.codex/skills/`，而是走回传流程：

1. 找到 pack 对应的 GitHub repo/path
2. 把本地 pack 改动映射回 editable repo clone
3. 跑 `test` / `quality-gate`
4. 生成 patch、commit 或 PR
5. 推回 GitHub 主库

## 6. Publish-Back 的最小职责

一个可用的 `publish-back` 工作流至少要做这几件事：

1. 识别本地 pack 身份
2. 判断当前修改是否来自安装目录
3. 找到对应 upstream repo 和 path
4. 把改动复制或转译到 repo clone
5. 执行验证
6. 产出：
   - git commit
   - patch bundle
   - draft PR

## 7. 建议补充的 pack 元数据

为了支持 publish-back，建议在每个 pack 的 `pack.json` 中补充 upstream 信息：

```json
{
  "pack_name": "tax-pack-rs-einvoice",
  "jurisdiction": "RS",
  "tax_domain": "einvoice",
  "entry_profile": "rs-srbdt-ext-2025",
  "default_family": "en16931_ubl",
  "runtime_package": "tax_parser_runtime",
  "upstream": {
    "repo": "YouyuiSS/gec-ai",
    "path": "skills/tax-pack-rs-einvoice",
    "core_path": "skills/tax-parser-core",
    "default_branch": "main"
  }
}
```

建议同时记录安装来源：

```json
{
  "installed_from": {
    "ref": "main",
    "commit": "<installed_commit_sha>"
  }
}
```

这样本地副本至少知道：

- 自己来自哪个 repo
- 对应 repo 里的哪个 path
- 安装时基于哪个 commit

## 8. 推荐的 publish-back 工作流

### 8.1 最稳妥流程

1. 用户在本地运行 pack 或修 pack
2. 如果需要长期修复，切换到 repo clone 中对应 pack 路径
3. 把改动同步到 repo clone
4. 在 repo clone 中执行：
   - `test`
   - `quality-gate`
5. 验证通过后：
   - commit
   - push
   - draft PR

### 8.2 如果用户只改了安装目录

可以允许一个中间态：

1. 从安装目录导出 patch bundle
2. 应用到 repo clone
3. 再走标准 git 流程

也就是说：

- 允许临时在安装目录实验
- 但正式发布必须回到 repo clone

## 9. 不推荐的方案

### 9.1 直接双向同步安装目录到 GitHub

不推荐，因为：

- 风险太大
- 缺少审核
- 很难保证 baseline 和 gate 完整执行

### 9.2 让 GitHub 被动依赖用户本地变化

不推荐，因为：

- GitHub 无法自己发现法规变化
- 一旦本地没人修，中央永远不知道源已经变了

## 10. 推荐的下一步落地

建议分三步做：

### Step 1

先补 metadata：

- 给 pack `pack.json` 加 `upstream`
- 记录安装来源 commit

### Step 2

新增一个 workflow skill：

- 负责把本地 pack 改动回传到 repo clone
- 强制走 `test` 和 `quality-gate`

### Step 3

再决定是否需要脚本化：

- `export-local-pack-patch.py`
- `publish-pack-update.py`

只有当手工流程已经明确后，才值得把它写成脚本。

## 11. 当前推荐理解

一句话概括：

> 本地安装 skill 是运行副本，GitHub repo 是主库，publish-back 是把“本地修复”显式回传到主库的受控流程。
