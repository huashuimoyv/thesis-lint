# thesis-lint —— 毕业论文「国标体检」工具

[![CI](https://github.com/huashuimoyv/thesis-lint/actions/workflows/ci.yml/badge.svg)](./actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

检查 **Word (.docx) 论文**的参考文献是否符合 **GB/T 7714-2025**《信息与文献 参考文献著录规则》。

现有的国标格式工具几乎都服务于 LaTeX 用户，而大多数中国毕业生用 Word 写论文，
只能靠肉眼对照模板逐条检查。thesis-lint 想改变这件事：

```console
$ thesislint 我的论文.docx
📄 我的论文.docx —— 参考文献共 42 条

[7]（第 133 行）李四. 论文名称. 学报, 2024.
    ❌ E002: 缺少文献类型标识，如 [J]、[M]、[D]、[C]、[EB/OL]

[12]（第 138 行）张三, 李四, 王五, 赵六. 某某研究[J]. 学报, 2024, 1(1): 1-9
    ⚠️ W003: 作者超过 3 人时应只列前 3 名，后加 “, 等”（GB/T 7714 第 8.1.2 条）
    ⚠️ W006: 条目未以句点“.”结尾

体检结果：40 条通过，1 个错误，2 个警告
```

## 安装

```bash
pip install thesis-lint   # 发布 PyPI 后可用；当前可从源码安装：
pip install git+https://github.com/huashuimoyv/thesis-lint.git
```

要求 Python 3.10+。

## 使用

```bash
thesislint 论文.docx                  # 文本报告（默认）
thesislint 论文.docx --format md      # Markdown 报告，适合贴进 issue / PR
thesislint 论文.docx --format json    # JSON，方便接入其他工具
thesislint 论文.docx --strict         # CI 中使用：有警告也算失败
```

退出码：`0` 通过；`1` 有错误（或 `--strict` 下有警告）；`2` 文件/用法问题。

## 目前能查出的问题

| 级别 | 规则 |
|------|------|
| ERROR | 缺少序号 `[n]`、缺少文献类型标识（`[J]`/`[M]`…）、电子资源缺网址、缺出版年份、条目序号重复 |
| WARN | 西文作者未用“姓前名缩写”、作者超 3 人未用“等”、全角标点、未以句点结尾、电子资源缺引用日期、序号跳号 |

## Roadmap

- [ ] 更多字段级规则：页码格式、出版社与出版地校验、DOI 规范
- [ ] 正文引用 `[1][2]` 与文献表交叉核对
- [ ] 图表编号连续性、公式编号检查
- [ ] 学校规则预设包（`rules/<学校>.json`），欢迎第一所你的学校！
- [ ] 提供 Web 版与 GitHub Action（在 PR 里自动评论体检报告）

## 贡献

规则集还不够全——这正是社区最能出力的地方。发现误报/漏报时，
欢迎提 issue 附上出错条目原文；提交新规则请附带对应测试用例。

开发：

```bash
git clone https://github.com/huashuimoyv/thesis-lint.git
cd thesis-lint
pip install -e ".[dev]"
pytest
```

## License

[MIT](./LICENSE)
