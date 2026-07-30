# 复杂文档 RAG 入库（第一阶段）

当前入库链路不再直接把 PDF/DOCX 压平成一大段文本，而是先生成统一的 `DocumentBlock`：标题、正文、列表、表格、图片和噪声都保留页码、坐标、阅读顺序与 OCR 标记。随后只渲染 `should_index=true` 的块交给现有分块、Embedding、关键词索引和混合检索。

## 已覆盖范围

- DOCX：按文档原顺序读取标题、段落、列表和表格；页眉页脚作为噪声保留但不索引。
- 原生 PDF：按坐标恢复阅读顺序，提取表格单元格，过滤跨页重复页眉、页脚和页码。
- 扫描 PDF：页面原生文字过少时才尝试 OCR；OCR 块会记录 `ocr_used`。图片本身暂不做视觉描述。
- 溯源：`course_material_blocks` 保存解析块，chunk 的 `source_block_ids_json` 指回原始块，搜索 citation 返回 `source_block_ids`。
- 安全边界：文档中的“忽略之前指令”等文字仍是待检索数据，不会被解析器当作系统命令执行。提示词隔离仍由 Agent/RAG 上下文层负责。

## OCR 配置

PyMuPDF 调用系统级 Tesseract，本项目不会静默下载可执行文件。Windows 需要单独安装 Tesseract 和 `chi_sim`、`eng` 语言数据，再设置：

```dotenv
RAG_OCR_LANGUAGE=chi_sim+eng
RAG_OCR_DPI=200
RAG_OCR_TESSDATA=C:\Program Files\Tesseract-OCR\tessdata
```

若扫描件需要 OCR 但运行环境不可用，资料会进入可重试的 `failed` 状态，并显示包含 Tesseract 的明确错误，而不是建立空索引。

## 测试方法

黄金测试包含复杂 DOCX、带表格和重复页眉页脚的 PDF，以及图片型扫描 PDF。二进制样本由固定脚本生成，人工标准答案保存在 `tests/fixtures/complex_documents/manifest.json`。

```powershell
.venv\Scripts\python.exe -m pytest tests\test_complex_document_parser.py -q

.venv\Scripts\python.exe -m scripts.evaluate_document_parsing `
  var\complex-doc-fixtures --build-fixtures --skip-ocr `
  --output var\complex-doc-fixtures\report.json
```

安装 Tesseract 后去掉 `--skip-ocr`，即可把真实 OCR 纳入质量门禁。指标包括正文召回率、噪声排除率、表格单元格召回率和阅读顺序准确率；评测标准不会进入 RAG 索引。
