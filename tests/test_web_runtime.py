"""Run the page's actual theme code in a minimal JS host, without network or a browser."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
HTML = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")
THEME = HTML.split("  const THEME_KEY = ", 1)[1].split("  function setStage(", 1)[0]
THEME = "  const THEME_KEY = " + THEME
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for JS runtime tests")

HOST = r"""
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const root = {dataset: {}};
const callbacks = {};
const button = {addEventListener: (name, fn) => { callbacks[name] = fn; }};
const saved = [];
const media = {matches: false, addEventListener: () => {}};
const storage = {
  getItem: () => { if (input.failure === 'read') throw Error('denied'); return input.stored; },
  setItem: (key, value) => { if (input.failure === 'write') throw Error('full'); saved.push([key, value]); }
};
const host = {document: {documentElement: root}, $: () => button, matchMedia: () => media};
Object.defineProperty(host, 'localStorage', {get: () => {
  if (input.failure === 'access') throw Error('denied');
  return storage;
}});
const states = [];
const snapshot = () => ({theme: root.dataset.theme || 'auto', title: button.title});
let error = null;
try {
  vm.runInNewContext(input.source, host);
  states.push(snapshot());
  for (let i = 0; i < input.clicks; i++) { callbacks.click(); states.push(snapshot()); }
} catch (exception) { error = exception.message; }
process.stdout.write(JSON.stringify({error, states, saved}));
"""


def theme_result(*, failure=None, stored=None, clicks=3):
    process = subprocess.run(
        [NODE, "-e", HOST],
        input=json.dumps({"source": THEME, "failure": failure, "stored": stored, "clicks": clicks}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=10,
    )
    return json.loads(process.stdout)


@pytest.mark.parametrize("failure", ["access", "read", "write"])
def test_theme_works_when_browser_storage_is_unavailable(failure):
    result = theme_result(failure=failure)
    assert result["error"] is None
    assert [state["theme"] for state in result["states"]] == ["auto", "light", "dark", "auto"]


@pytest.mark.parametrize("stored", ["broken", "LIGHT", "null"])
def test_invalid_saved_theme_falls_back_to_system(stored):
    result = theme_result(stored=stored, clicks=1)
    assert result["error"] is None
    assert [state["theme"] for state in result["states"]] == ["auto", "light"]


@pytest.mark.parametrize("stored", ["auto", "light", "dark"])
def test_valid_theme_is_restored_and_next_choice_is_saved(stored):
    result = theme_result(stored=stored, clicks=1)
    expected = {"auto": "light", "light": "dark", "dark": "auto"}[stored]
    assert result["error"] is None
    assert [state["theme"] for state in result["states"]] == [stored, expected]
    assert result["saved"] == [["thesislint-theme", expected]]


COPY_HOST = r"""
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const callbacks = {};
const messages = [];
const copied = [];
const navigator = {};
if (input.mode !== 'missing') navigator.clipboard = {writeText: text => {
  if (input.mode === 'sync') throw Error('blocked');
  if (input.mode === 'reject') return Promise.reject(Error('blocked'));
  copied.push(text); return Promise.resolve();
}};
const host = {navigator, reportText: 'complete report', fixData: '[4] original number',
  $: id => ({addEventListener: (_, callback) => {callbacks[id] = callback;}}),
  setStage: (text, spin) => messages.push({text, spin})};
(async () => {
  let error = null;
  try {
    vm.runInNewContext(input.source, host);
    await callbacks[input.button]();
    await new Promise(resolve => setImmediate(resolve));
  } catch (exception) {error = exception.message;}
  process.stdout.write(JSON.stringify({error, messages, copied}));
})();
"""


@pytest.mark.parametrize("button,next_button", [("btnCopy", "btnMd"), ("btnFixCopy", "btnFixTxt")])
@pytest.mark.parametrize("mode", ["missing", "sync", "reject", "success"])
def test_copy_actions_handle_unavailable_or_denied_clipboard(button, next_button, mode):
    source = HTML.split(f'  $("{button}").addEventListener', 1)[1].split(
        f'  $("{next_button}").addEventListener', 1
    )[0]
    source = f'  $("{button}").addEventListener' + source
    if "  async function copyText(" in HTML:
        helper = HTML.split("  async function copyText(", 1)[1].split(
            "  /* ---------- 事件绑定 ---------- */", 1
        )[0]
        source = "  async function copyText(" + helper + source
    process = subprocess.run(
        [NODE, "-e", COPY_HOST],
        input=json.dumps({"source": source, "button": button, "mode": mode}),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
        timeout=10,
    )
    result = json.loads(process.stdout)
    assert result["error"] is None
    assert len(result["messages"]) == 1
    assert result["messages"][0]["spin"] is False
    if mode == "success":
        assert "已复制" in result["messages"][0]["text"]
        assert result["copied"] == [
            "complete report" if button == "btnCopy" else "[4] original number"
        ]
    else:
        assert "复制失败，请手动选择" in result["messages"][0]["text"]
        assert result["copied"] == []
