# 复杂文档解析黄金测试包

`manifest.json` 是人工可审查的标准答案，列出必须保留的正文、必须排除的噪声、表格单元格和阅读顺序。二进制文档由固定脚本生成，不把测试答案送入 RAG 索引。

```powershell
.venv\Scripts\python.exe -m scripts.build_complex_document_fixtures var\complex-doc-fixtures
.venv\Scripts\python.exe -m scripts.evaluate_document_parsing var\complex-doc-fixtures --skip-ocr
```

真实扫描件评测不加 `--skip-ocr`，并要求本机安装 Tesseract 与 `chi_sim`、`eng` 语言包。单元测试使用可注入 OCR 提供器验证扫描页分支，因此 CI 不依赖系统级 Tesseract。
