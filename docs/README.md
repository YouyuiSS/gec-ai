# Docs Index

当前 `docs/` 目录里同时存在三类文档：

1. 当前工作台和可安装 skill 的现行文档
2. 迁移和拆分方案文档
3. 早期设计或历史背景文档

下面按“推荐优先级”整理。

## 1. 当前有效文档

这些是当前结构下最应该先看的文档。

### 1.1 工作台与使用

- [tax_skill_frontdoor_state_machine_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_frontdoor_state_machine_v1.md)
  前台单入口、后台状态分流的正式方案。
- [tax_skill_workbench_architecture_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_workbench_architecture_v1.md)
  当前 `core + pack + harness + monitor` 工作台的正式架构说明。
- [tax_skill_install_guide.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_install_guide.md)
  对外安装和运行说明，面向 skill 使用者。
- [tax_skill_publish_back_architecture_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_publish_back_architecture_v1.md)
  解释安装到本地后的 pack 如何通过受控流程回传到 GitHub 主库。

### 1.2 当前拆分方案

- [tax_skill_core_pack_split_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_core_pack_split_v1.md)
  为什么从一个大 skill 演进为 `core + pack`。
- [tax_skill_multi_install_migration_plan_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_multi_install_migration_plan_v1.md)
  如何把当前 skill 迁到多个可安装 skill。

## 2. 迁移参考文档

这些文档仍然有价值，但更偏迁移过程和中间状态。

- [tax_skill_family_overlay_migration_plan_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_family_overlay_migration_plan_v1.md)
  从平铺 extractor 迁到 `family + overlay` 的中间迁移方案。

## 3. 系统级背景文档

这些文档描述的是更大范围的系统，不只是当前可安装 skill。

- [tax_regulation_update_system.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_regulation_update_system.md)
  税法持续更新系统的版本化、证据化和发布思路。
- [global_tax_implementation_layer_design_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/global_tax_implementation_layer_design_v1.md)
  全球税法实施层的更高层设计。

## 4. 历史设计文档

这些文档主要用于理解项目的演化背景，不建议当作当前实现的主说明。

- [opencode_tax_skill_design_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/opencode_tax_skill_design_v1.md)
  早期单体 `tax-law-parser` skill 的正式设计。
- [web_parser_profile_repair_v0.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/web_parser_profile_repair_v0.md)
  web 侧 profile repair 方向的早期方案。

## 5. 推荐阅读顺序

如果你现在要理解或继续扩展这套工作台，推荐顺序如下：

1. [tax_skill_frontdoor_state_machine_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_frontdoor_state_machine_v1.md)
2. [tax_skill_workbench_architecture_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_workbench_architecture_v1.md)
3. [tax_skill_install_guide.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_install_guide.md)
4. [tax_skill_publish_back_architecture_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_publish_back_architecture_v1.md)
5. [tax_skill_core_pack_split_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_core_pack_split_v1.md)
6. [tax_skill_multi_install_migration_plan_v1.md](/Users/xueyunsong/Documents/GitHub/gec-ai/docs/tax_skill_multi_install_migration_plan_v1.md)
7. 需要追历史时，再看第 3、4 类文档

## 6. 当前文档边界

当前建议把文档职责收敛成这样：

- `workbench architecture`
  解释当前结构和分层职责
- `install guide`
  解释怎么安装和运行
- `split / migration plans`
  解释为什么拆、怎么迁
- `historical docs`
  解释项目为什么会演化成现在这样

这样后面再加文档时，就不会把“当前操作说明”和“历史设计稿”混在一起。
