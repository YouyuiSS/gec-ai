# Tax Field Extraction Notes

- 输出范围：仅抽取原子字段 `BT-*` 和 `HR-BT-*`，共 `174` 条；未包含 `BG-* / HR-BG-*` 分组行。
- 主字段来源：`Specification-of-the-usecase-of-eInvoice-with-HR-extensions.pdf`；语义数据类型与金额精度参考：`SR EN 16931-1+A1_2020.pdf`。
- `值集校验取值` 优先写入文档中显式出现的布尔值、代码表引用、枚举项或备注；若文档只给出代码表名称，则保留代码表引用，不强行展开全部值。
- `最小字符长度 / 最大字符长度 / 小数位精度` 只在文档显式给出，或能从明确格式规则直接推出时填写；其余留空，表示文档未显式规定。
- `报送税局字段层级` 同时保留 `Invoice` 和 `CreditNote` 两条 UBL 路径。
