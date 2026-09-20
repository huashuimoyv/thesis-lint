"""从目标标签的更新日志生成 Release 说明；缺失条目时阻止发布。"""

import argparse
import re
from pathlib import Path
from urllib.parse import quote


def extract_version_section(changelog: str, tag: str) -> str:
    lines = changelog.splitlines()
    headings = []
    fence = ""
    for index, line in enumerate(lines):
        marker = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if fence:
            # 只有同类、至少等长且后面没有内容的围栏才能结束代码块。
            if (
                marker
                and marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip(" \t")
            ):
                fence = ""
            continue
        if marker and (marker[1][0] == "~" or "`" not in marker[2]):
            fence = marker[1]
            continue
        if match := re.fullmatch(r"##[ \t]+(.+)", line):
            headings.append((index, match[1].strip()))
    matches = [index for index, heading in headings if heading == tag]
    if len(matches) != 1:
        raise ValueError(f"CHANGELOG must contain exactly one '## {tag}' section")
    start = matches[0]
    end = next((index for index, _ in headings if index > start), len(lines))
    section = "\n".join(lines[start + 1 : end]).strip()
    if not section:
        raise ValueError(f"CHANGELOG section for {tag} is empty")
    return section


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--zipname", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--server-url", default="https://github.com")
    parser.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    parser.add_argument("--output", type=Path, default=Path("release_notes.md"))
    args = parser.parse_args()
    try:
        changes = extract_version_section(args.changelog.read_text(encoding="utf-8"), args.tag)
        source = f"{args.server_url.rstrip('/')}/{args.repository}/blob/{quote(args.tag, safe='')}"
        notes = f"""毕业论文「国标体检」工具 **{args.tag}** —— 检查 Word (.docx) 论文参考文献是否符合 GB/T 7714-2025。

## 本版更新

{changes}

## 便携版说明

- 免安装、无需 Python，Windows 10+ x64
- 解压后双击 `thesislint.exe` 使用黑白双主题图形界面，也支持命令行
- 程序未签名；若系统提示，请先确认来自本仓库 Release 并核对 SHA256，再自行决定是否运行

## 校验

```
{args.sha256} *{args.zipname}
```

完整变更与源码见 [CHANGELOG]({source}/CHANGELOG.md)。
"""
        args.output.write_text(notes, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
