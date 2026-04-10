# Overlays

overlay 负责国家或地区差异，不负责重写整个 family parser。

overlay 应该修改的内容：

- 表头语言
- 本地 note 前缀
- 本地字段名修正
- 本地特殊路径修补
- 少量本地 continuation 规则

overlay 不应修改的内容：

- 通用表格遍历
- 通用路径折行拼接
- 通用去重和归一化

当前第一阶段 overlay：

- `profiles/families/en16931_ubl/hr_overlay.py`
- `profiles/families/en16931_ubl/rs_overlay.py`
