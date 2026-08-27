# thesis-lint 项目上下文（给 AI 助手的交接文档）

> 本文件由上一个会话生成，用于无缝续接开发。请先通读再动手。

## 项目是什么

**毕业论文「国标体检」工具**：读取 Word (.docx) 论文，自动检查参考文献是否符合 GB/T 7714-2025 国标。
差异化定位：现有国标工具全是 LaTeX 圈的（最火 1400+ 星），**Word 用户没有工具**，本项目填这个空白。

- 本地路径：`C:\Users\Ameath\.zcode\workspace\default\thesis-lint`
- 远端：`github.com/huashuimoyv/thesis-lint`（公开仓库，MIT）
- 当前版本：v0.2.0（GitHub Release 含免安装便携版 exe，双击打开图形界面）
- 在线版：https://huashuimoyv.github.io/thesis-lint/ （Pyodide 跑同一套 Python 规则，纯前端不上传）

## 架构（src 布局）

```
src/thesislint/
  gui.py        # 图形界面（v0.2.0+）：拖拽/选文件 → 窗口内报告 → 复制/导出 Markdown。
                #   双模式分发规则（cli.main）：无参数=GUI；单个 docx 参数且 _launched_from_explorer()=GUI
                #   （拖到 exe 图标）；其余=命令行。GUI 后台线程分析不冻 UI。
                #   测试钩子：环境变量 THESISLINT_GUI_AUTOCLOSE_MS 让窗口自动关闭（冒烟测试用）。
                #   拖拽依赖 tkinterdnd2（仅 win32 marker），失败自动降级为纯按钮模式。
  extractor.py  # 定位"参考文献"章节，逐条提取（自动合并 Word 折行条目），保留 [n] 序号原文
  checker.py    # 11 条规则引擎，ERROR/WARN 两级：缺序号/类型标识/年份/网址、序号重复跳号(段落级)、
                #   作者>3人未加",等"(认可 et al.)、西文姓名未缩写、全角标点、缺尾句点、/OL缺引用日期
  report.py     # Report/EntryResult 数据类 + text/markdown/json 三种报告
  cli.py        # argparse 入口；--section/--format/--strict；退出码 0过/1错/2用法
tests/          # 22 个测试全绿（checker 规则单测 + 用 python-docx 现场造 docx 的端到端测试）
build/portable_entry.py          # PyInstaller 构建入口
build/使用说明.txt               # 便携版压缩包内附的说明
.github/workflows/ci.yml        # pytest 矩阵 (3.10/3.12/3.14)
.github/workflows/release.yml   # 打 v* tag 自动构建便携版并发 Release
.github/assets/demo.svg         # README 头图（手绘终端风格，内容与真实 CLI 输出逐字对齐）
web/index.html                  # 网页版（v0.2.x+）：Pyodide + micropip 装本地 wheels，纯前端
.github/workflows/pages.yml     # 构建 wheel + 收集 python-docx/typing_extensions wheel + 部署 Pages
                                #   （lxml 用 Pyodide 官方 wasm 包，manifest.json 由 CI 生成供 JS 读取）
```

## 常用命令（本机环境）

```bash
cd C:\Users\Ameath\.zcode\workspace\default\thesis-lint
./.venv/Scripts/python.exe -m pytest                          # 跑测试（venv 是 uv 建的，Python 3.12）
./.venv/Scripts/python.exe -m thesislint.cli 某论文.docx       # 本地运行 CLI
./.venv/Scripts/pyinstaller.exe --onefile --clean --noconfirm --name thesislint build/portable_entry.py
```

- 装依赖用 uv：`uv pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple`（国内走清华镜像）
- 本机网络**直连不了 GitHub**，代理 `http://127.0.0.1:7897`（Clash Verge，用户需手动开启）。
  git 已做 scoped 代理：仅 github.com 走代理（`http.https://github.com.proxy` 全局配置）。

## 发布流程（已全自动）

```bash
# 改代码 → 更新 pyproject.toml 的 version → 然后：
git tag v0.1.1 && git push origin v0.1.1   # release.yml 自动：测试→PyInstaller→zip+SHA256→创建 Release
```

- release.yml 有版本守卫：tag 与 pyproject version 不一致会直接失败
- 干跑验证：`gh workflow run release.yml --ref main`（只构建产出 Artifact，不发版）
- gh CLI 在 `C:\Users\Ameath\Tools\gh\Program Files\GitHub CLI\gh.exe`（已加入用户 PATH），
  账号 huashuimoyv 已登录（含 workflow scope）；操作 GitHub 时记得带 `HTTPS_PROXY=http://127.0.0.1:7897`

## 设计决策（勿破坏）

1. **ERROR = 确定违反国标；WARN = 疑似/建议**。`--strict` 时 WARN 也算失败。新规则先想清楚放哪级
2. 条目文本**保留完整原文**（含 `[n]` 前缀），序号解析是 checker 的职责（extractor 只管提取）
3. 每条 Issue 带 code（E001-E004/W001-W006/S001-S002），新增规则继续编号并**必须带测试用例**
4. CLI 输出**禁用 emoji**（目标用户多用老式 cmd，GBK 环境已踩过坑——启动时强制 UTF-8 stdio + errors=replace）
5. 报告中的输出示例与 demo.svg 内容保持逐字一致

## Roadmap（按价值排序，尚未实现）

0. ~~双击 GUI~~（v0.2.0 已完成）；~~网页版~~（已上线 Pyodide + GitHub Pages）
1. 更多字段级规则：页码格式、出版地：出版社校验、DOI 规范
2. 正文引用 `[1][2]` 与文献表交叉核对
3. 图表编号连续性、公式编号检查
4. 学校规则预设包 `rules/<学校>.json`（增长飞轮：每个毕业生有动力提交自己学校）
5. GitHub Action：PR 里自动评论体检报告
6. 发布 PyPI（`pip install thesis-lint`，名字预留的是 thesis-lint）

## 已踩过的坑（勿重蹈）

- `.gitignore` 写了宽泛的 `build/` 导致构建入口没进仓库、云端构建失败 → 现在只忽略 `build/thesislint/` 和 `build/*.spec`
- GitHub OAuth token 默认没有 `workflow` scope，推送含 workflow 文件会被拒（已通过 `gh auth refresh -s workflow` 解决）
- `python -m zipfile -c` 在 release.yml 里打包（Windows runner 没有 zip 命令）

## 本机 MCP 配置（ZCode 用，供参考）

`C:\Users\Ameath\.zcode\cli\config.json`：zotero（本地模式，需 Zotero 运行）+ anysearch（远程搜索，带 API Key）。
