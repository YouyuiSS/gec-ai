# Parser Families

当前实施层优先按文档家族拆 parser，不按国家直接平铺。

第一阶段只正式支持：

- `en16931_ubl`

适用特征：

- 表格化 PDF
- `BT-* / BG-* / BR-*`
- UBL 路径直接出现在表格或路径行中
- 国家差异主要是表头语言、本地注释、本地扩展字段

未来家族可扩展为：

- `peppol_pint`
- `schema_first`
- `clearance_html`
