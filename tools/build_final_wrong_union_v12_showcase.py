from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


SRC_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v10-embedded")
OUT_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v12-embedded")
SRC_HTML = SRC_DIR / "final_wrong_union_horizontal_review_embedded.html"
OUT_HTML = OUT_DIR / "final_wrong_union_horizontal_review_embedded.html"

OLD_NAME = "团队版灵犀"
NEW_NAME = "灵犀"


def update_css(text: str) -> str:
    text = text.replace(
        ":root{--bg:#f6f7f9;--panel:#fff;--line:#d9dee7;--text:#172033;--muted:#5f6b7a;--red:#b42318;--blue:#175cd3;}",
        ":root{--bg:#f4f7ff;--panel:#ffffff;--line:#d7e3ff;--text:#172033;--muted:#5f6b7a;--red:#cc2b2b;--blue:#2f6fed;--green:#0f9f61;--red-bg:#ffe7e7;--green-bg:#e6f7ee;--soft:#eef4ff;}",
        1,
    )
    text = text.replace(
        "*{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;font-family:Segoe UI,Microsoft YaHei,Arial,sans-serif;background:var(--bg);color:var(--text)}",
        "*{box-sizing:border-box} html{scroll-behavior:smooth} body{margin:0;font-family:Segoe UI,Microsoft YaHei,Arial,sans-serif;background:linear-gradient(180deg,#f8fbff 0%,#edf3ff 100%);color:var(--text)}",
        1,
    )
    replacements = {
        "header{position:sticky;top:0;z-index:20;background:#ffffffee;backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:14px 22px}":
            "header{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:18px 26px;box-shadow:0 10px 28px rgba(47,111,237,.06)}",
        "h1{margin:0 0 6px;font-size:23px}":
            "h1{margin:0 0 8px;font-size:26px;color:#294fa7}",
        ".summary{color:var(--muted);line-height:1.5;max-width:1420px}":
            ".summary{color:var(--muted);line-height:1.6;max-width:1420px;font-size:14px}",
        ".layout{display:grid;grid-template-columns:300px minmax(0,1fr);gap:18px;max-width:1780px;margin:0 auto;padding:18px 22px 48px}":
            ".layout{display:grid;grid-template-columns:310px minmax(0,1fr);gap:24px;max-width:1880px;margin:0 auto;padding:22px 26px 56px}",
        "aside{position:sticky;top:92px;align-self:start;height:calc(100vh - 110px);overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px}":
            "aside{position:sticky;top:100px;align-self:start;height:calc(100vh - 118px);overflow:auto;background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:24px;padding:16px 16px 18px;box-shadow:0 18px 42px rgba(47,111,237,.08)}",
        ".nav-module{border-top:1px solid var(--line);padding-top:8px;margin-top:8px}":
            ".nav-module{border-top:1px solid #e6edff;padding-top:10px;margin-top:10px}",
        ".nav-cases a{display:block;color:#344054;text-decoration:none;font-size:12px;padding:4px 2px;border-radius:5px}":
            ".nav-cases a{display:block;color:#344054;text-decoration:none;font-size:12px;padding:6px 8px;border-radius:10px}",
        ".nav-cases a:hover{background:#eef2f7}":
            ".nav-cases a:hover{background:#eef4ff}",
        ".mini{display:inline-block;font-size:10px;border-radius:4px;padding:1px 3px;margin-left:2px}":
            ".mini{display:inline-block;font-size:10px;border-radius:999px;padding:2px 6px;margin-left:4px}",
        ".overview{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:18px}.overview-title{font-size:15px;margin:2px 0 10px}.scope-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:6px 0 10px}.scope-grid div{border:1px solid var(--line);background:#fbfcfe;border-radius:7px;padding:9px}.scope-grid b{display:block;font-size:12px;color:#344054;margin-bottom:4px}.scope-grid span{font-size:13px}.scope-note{font-size:13px;color:var(--muted);line-height:1.5;margin:8px 0 14px}":
            ".overview{background:var(--panel);border:1px solid var(--line);border-radius:26px;padding:20px 22px;margin-bottom:24px;box-shadow:0 18px 46px rgba(47,111,237,.08)}.overview-title{font-size:16px;margin:2px 0 12px;color:#355bb5}.scope-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:10px 0 12px}.scope-grid div{border:1px solid var(--line);background:#f8fbff;border-radius:18px;padding:12px}.scope-grid b{display:block;font-size:12px;color:#355bb5;margin-bottom:6px}.scope-grid span{font-size:13px}.scope-note{font-size:13px;color:var(--muted);line-height:1.6;margin:10px 0 16px}",
        "th,td{border-bottom:1px solid var(--line);text-align:left;padding:7px;vertical-align:top} th{background:#f0f3f8}":
            "th,td{border-bottom:1px solid var(--line);text-align:left;padding:10px 9px;vertical-align:top} th{background:#f4f7ff}",
        ".module-heading{margin:22px 0 10px;font-size:20px}":
            ".module-heading{margin:28px 0 14px;font-size:23px;color:#294fa7}",
        ".module-heading span{color:var(--muted);font-size:13px;font-weight:500}":
            ".module-heading span{color:var(--muted);font-size:13px;font-weight:500;margin-left:6px}",
        ".case-card{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin:14px 0 18px;overflow:hidden;scroll-margin-top:105px}":
            ".case-card{background:rgba(255,255,255,.98);border:1px solid var(--line);border-radius:28px;margin:18px 0 28px;overflow:hidden;scroll-margin-top:112px;box-shadow:0 22px 52px rgba(47,111,237,.08)}",
        ".case-head{padding:13px 15px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:10px;flex-wrap:wrap}":
            ".case-head{padding:20px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:linear-gradient(180deg,#ffffff 0%,#f7fbff 100%)}",
        ".case-no,.case-id{font-weight:700;background:#eef2f7;padding:4px 8px;border-radius:6px}":
            ".case-no,.case-id{font-weight:700;background:#edf4ff;padding:6px 10px;border-radius:999px;color:#355bb5}",
        ".case-head h3{font-size:16px;margin:0;flex:1 1 420px}":
            ".case-head h3{font-size:19px;margin:0;flex:1 1 420px;line-height:1.45}",
        ".status-chip{display:inline-block;border-radius:999px;padding:4px 8px;font-size:12px;font-weight:700} .status-chip.wrong{background:#fff1f0;color:var(--red);border:1px solid #ffccc7} .status-chip.ok{background:#eff6ff;color:var(--blue);border:1px solid #bfdbfe}":
            ".status-chip{display:inline-block;border-radius:999px;padding:6px 12px;font-size:12px;font-weight:700} .status-chip.wrong{background:var(--red-bg);color:var(--red);border:0} .status-chip.ok{background:#edf4ff;color:var(--blue);border:0}",
        ".case-meta{padding:12px 15px;display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:12px;background:#fbfcfe;border-bottom:1px solid var(--line)}":
            ".case-meta{padding:16px 20px;display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:16px;background:#f8fbff;border-bottom:1px solid var(--line)}",
        "pre{white-space:pre-wrap;margin:6px 0 0;font-family:Consolas,Microsoft YaHei,monospace;font-size:13px;line-height:1.45;color:#243045}":
            "pre{white-space:pre-wrap;margin:6px 0 0;font-family:Consolas,Microsoft YaHei,monospace;font-size:13px;line-height:1.6;color:#243045}",
        ".products{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}":
            ".products{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;padding:22px;background:linear-gradient(180deg,#f7fbff 0%,#eef4ff 100%)}",
        ".prod-card{padding:14px;border-right:1px solid var(--line);min-width:0} .prod-card:last-child{border-right:0} .prod-card h3{margin:0 0 8px;font-size:16px}":
            ".prod-card{padding:18px 18px 20px;border:1px solid var(--line);border-radius:26px;min-width:0;background:#fff;box-shadow:0 16px 40px rgba(47,111,237,.08);display:flex;flex-direction:column;gap:10px} .prod-card:last-child{border-right:1px solid var(--line)} .prod-card h3{margin:0;font-size:22px;line-height:1.25;color:#1a2f61}",
        ".badge{display:inline-block;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:700} .badge.fail{background:#fff1f0;color:var(--red);border:1px solid #ffccc7} .badge.compare{background:#eff6ff;color:var(--blue);border:1px solid #bfdbfe}":
            ".badge{display:inline-block;border-radius:999px;padding:8px 16px;font-size:14px;font-weight:700} .badge.fail{background:var(--red-bg);color:var(--red);border:0} .badge.compare{background:var(--green-bg);color:var(--green);border:0}",
        ".wrong-reason{margin-top:8px;padding:8px;border-radius:6px;color:var(--red);background:#fff5f5;border:1px solid #fecdca;font-size:13px;line-height:1.45}":
            ".wrong-reason{margin-top:4px;padding:12px 14px;border-radius:16px;color:var(--red);background:#fff5f5;border:1px solid #ffd3d3;font-size:14px;line-height:1.6;font-weight:700}",
        ".label{font-weight:700;margin-top:10px;font-size:13px;color:#344054} .answer,.judge{margin-top:5px;padding:9px;border-radius:6px;background:#f8fafc;border:1px solid #e5e7eb;font-size:13px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}":
            ".label{font-weight:700;margin-top:4px;font-size:13px;color:#344054} .answer,.judge{margin-top:4px;padding:12px 14px;border-radius:16px;background:#f8fbff;border:1px solid #dbe7ff;font-size:13px;line-height:1.68;white-space:pre-wrap;overflow-wrap:anywhere}",
        ".shots{display:flex;gap:10px;overflow-x:auto;margin-top:12px;padding-bottom:6px} figure{margin:0;flex:0 0 250px;border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden} img{display:block;width:100%;height:510px;object-fit:contain;background:#0b1020} figcaption{font-size:11px;color:#667085;padding:6px 8px;word-break:break-all}":
            ".shots{display:flex;flex-direction:column;gap:16px;margin-top:2px;padding-bottom:0}.shots figure{margin:0 auto;width:min(100%,430px);padding:16px;border:1px solid #d7e3ff;border-radius:30px;background:linear-gradient(180deg,#f6f9ff 0%,#eef3ff 100%);box-shadow:0 18px 44px rgba(47,111,237,.12)}.shots a{display:block}.shots img{display:block;width:100%;height:auto;max-height:760px;aspect-ratio:1080/2244;object-fit:contain;background:#ffffff;border:10px solid #101828;border-radius:30px;box-shadow:0 14px 28px rgba(16,24,40,.16)}.shots figcaption{font-size:11px;color:#667085;padding:10px 4px 0;word-break:break-all;text-align:center}",
        ".backtop{position:fixed;right:18px;bottom:18px;background:#111827;color:white;text-decoration:none;padding:9px 12px;border-radius:999px;font-size:13px;z-index:30}":
            ".backtop{position:fixed;right:18px;bottom:18px;background:#1f3f8f;color:white;text-decoration:none;padding:10px 14px;border-radius:999px;font-size:13px;z-index:30;box-shadow:0 12px 24px rgba(31,63,143,.22)}",
        "@media(max-width:1200px){.layout{grid-template-columns:1fr} aside{position:static;height:auto} .case-meta,.products{grid-template-columns:1fr} .prod-card{border-right:0;border-bottom:1px solid var(--line)}}":
            "@media(max-width:1200px){.layout{grid-template-columns:1fr} aside{position:static;height:auto} .case-meta,.products{grid-template-columns:1fr} .products{padding:14px} .prod-card{border-right:1px solid var(--line)} .scope-grid{grid-template-columns:1fr 1fr}}",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def inject_showcase_css(text: str) -> str:
    marker = "</style>"
    extra = """
.showcase-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:6px}
.showcase-name{display:flex;align-items:center;min-width:0}
.showcase-badge{display:flex;align-items:center;justify-content:flex-end}
.showcase-summary{margin-top:2px;padding:12px 14px;border-radius:16px;font-size:14px;font-weight:700;line-height:1.6}
.showcase-summary.good{background:var(--green-bg);color:var(--green)}
.showcase-summary.bad{background:var(--red-bg);color:var(--red)}
.prod-card .label:first-of-type,.prod-card .answer:first-of-type{margin-top:0}
.prod-card .judge{background:#fbfcff}
.prod-card .answer,.prod-card .judge,.prod-card .wrong-reason,.showcase-summary{order:4}
.prod-card .shots{order:2}
.prod-card .wrong-reason{order:3}
"""
    return text.replace(marker, extra + marker, 1)


def update_strings(text: str) -> str:
    replacements = [
        (OLD_NAME, NEW_NAME),
        ("三产品最终不通过项并集横向复核 v10 单文件版", "三产品最终不通过项并集横向复核 v12 展示版"),
        ("phone2app.finalWrongUnion.v10.reviewDecisions", "phone2app.finalWrongUnion.v12.reviewDecisions"),
        ("const productOrder=['团队版灵犀','移动灵犀','豆包'];", "const productOrder=['灵犀','移动灵犀','豆包'];"),
        ("评测对象</b><span>团队版灵犀、移动灵犀、豆包</span>", "评测对象</b><span>灵犀、移动灵犀、豆包</span>"),
    ]
    for src, dst in replacements:
        text = text.replace(src, dst)
    return text


def inject_showcase_script(text: str) -> str:
    script = """
<script>
(function(){
  function moveAfter(node, anchor){
    if(node && anchor && node !== anchor){
      anchor.parentNode.insertBefore(node, anchor.nextSibling);
    }
  }
  function prettifyCards(){
    document.querySelectorAll('.prod-card').forEach((card)=>{
      if(card.dataset.showcaseReady==='1') return;
      card.dataset.showcaseReady='1';
      const title = card.querySelector('h3');
      const badge = card.querySelector('.badge');
      if(title && badge){
        const hero = document.createElement('div');
        hero.className = 'showcase-hero';
        hero.innerHTML = '<div class="showcase-name"></div><div class="showcase-badge"></div>';
        hero.querySelector('.showcase-name').appendChild(title);
        hero.querySelector('.showcase-badge').appendChild(badge);
        card.insertBefore(hero, card.firstChild);
      }
      const shots = card.querySelector('.shots');
      const reason = card.querySelector('.wrong-reason');
      if(shots){
        moveAfter(shots, card.firstChild);
      }
      if(reason && shots){
        moveAfter(reason, shots);
      }
      const answerLabel = [...card.querySelectorAll('.label')].find((el)=>el.textContent.includes('答案摘要'));
      const answer = card.querySelector('.answer');
      if(answer){
        const summary = document.createElement('div');
        summary.className = 'showcase-summary ' + (card.querySelector('.badge.fail') ? 'bad' : 'good');
        const prefix = card.querySelector('.badge.fail') ? '错误表现：' : '回答情况：';
        summary.textContent = prefix + ' ' + answer.textContent.trim().replace(/\\s+/g,' ').slice(0,110);
        if(answerLabel){
          card.insertBefore(summary, answerLabel);
        }else{
          card.appendChild(summary);
        }
      }
    });
  }
  window.addEventListener('DOMContentLoaded', prettifyCards);
})();
</script>
"""
    insert_after = "</script>\n<script>\n(function(){"
    if insert_after in text:
        return text.replace(insert_after, "</script>" + script + "\n<script>\n(function(){", 1)
    return text.replace("</body>", script + "</body>")


def rename_manifest_product_keys(mapping: dict[str, object]) -> dict[str, object]:
    renamed: dict[str, object] = {}
    for key, value in mapping.items():
        new_key = key
        if key == OLD_NAME:
            new_key = NEW_NAME
        elif key.startswith(f"{OLD_NAME}_"):
            new_key = key.replace(OLD_NAME, NEW_NAME, 1)
        renamed[new_key] = value
    return renamed


def update_manifest(path: Path) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["created_at"] = datetime.now().isoformat(timespec="seconds")
    data["version"] = "v12-showcase"
    if "output_html" in data:
        data["output_html"] = str(OUT_HTML.resolve())
        data["output_html_bytes"] = OUT_HTML.stat().st_size
    if isinstance(data.get("product_pass_wrong_summary"), dict):
        data["product_pass_wrong_summary"] = rename_manifest_product_keys(data["product_pass_wrong_summary"])
    if isinstance(data.get("module_scope_counts"), dict):
        data["module_scope_counts"] = {
            module_name: rename_manifest_product_keys(module_counts) if isinstance(module_counts, dict) else module_counts
            for module_name, module_counts in data["module_scope_counts"].items()
        }
    scope = data.get("test_scope")
    if isinstance(scope, dict) and isinstance(scope.get("products"), list):
        scope["products"] = [NEW_NAME if item == OLD_NAME else item for item in scope["products"]]
    rendered = json.dumps(data, ensure_ascii=False, indent=2).replace(OLD_NAME, NEW_NAME)
    path.write_text(rendered + "\n", encoding="utf-8")


def normalize_manifest_text(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(OLD_NAME, NEW_NAME), encoding="utf-8")


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    shutil.copytree(SRC_DIR, OUT_DIR)
    text = SRC_HTML.read_text(encoding="utf-8")
    text = update_css(text)
    text = inject_showcase_css(text)
    text = update_strings(text)
    text = inject_showcase_script(text)
    OUT_HTML.write_text(text, encoding="utf-8")
    manifest_paths = [
        OUT_DIR / "embedded_manifest.json",
        OUT_DIR / "final_wrong_union_horizontal_review_manifest.json",
    ]
    for manifest_path in manifest_paths:
        update_manifest(manifest_path)
        normalize_manifest_text(manifest_path)
    print(str(OUT_HTML))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
