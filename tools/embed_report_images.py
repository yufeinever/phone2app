from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import shutil
from pathlib import Path


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed local report images into a self-contained HTML report.")
    parser.add_argument("--src-html", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--out-name", default="final_wrong_union_horizontal_review_embedded.html")
    args = parser.parse_args()

    src_html = args.src_html
    src_dir = src_html.parent
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = out_dir / args.out_name

    text = src_html.read_text(encoding="utf-8")
    asset_refs = sorted(set(re.findall(r'(?:src|href)="(assets/[^"]+\.(?:png|jpg|jpeg|webp|gif))"', text, flags=re.I)))
    assets: dict[str, str] = {}
    missing: list[str] = []
    for ref in asset_refs:
        path = src_dir / ref
        if path.exists():
            assets[ref] = data_uri(path)
        else:
            missing.append(ref)

    def replace_attr(match: re.Match[str]) -> str:
        attr = match.group(1)
        ref = match.group(2)
        if ref not in assets:
            return match.group(0)
        return f'data-embedded-{attr}="{ref}"'

    text = re.sub(r'(src|href)="(assets/[^"]+\.(?:png|jpg|jpeg|webp|gif))"', replace_attr, text, flags=re.I)
    text = text.replace(
        "三产品最终不通过项并集横向复核 v8",
        "三产品最终不通过项并集横向复核 v8 单文件版",
    )

    bootstrap = f"""
<script id="embedded-assets" type="application/json">{json.dumps(assets, ensure_ascii=False, separators=(",", ":"))}</script>
<script>
(function () {{
  const raw = document.getElementById('embedded-assets');
  if (!raw) return;
  const assets = JSON.parse(raw.textContent || '{{}}');
  document.querySelectorAll('[data-embedded-src]').forEach((node) => {{
    const key = node.getAttribute('data-embedded-src');
    if (assets[key]) node.setAttribute('src', assets[key]);
  }});
  document.querySelectorAll('[data-embedded-href]').forEach((node) => {{
    const key = node.getAttribute('data-embedded-href');
    if (assets[key]) node.setAttribute('href', assets[key]);
  }});
}})();
</script>
"""
    text = text.replace("</body>", bootstrap + "</body>")
    out_html.write_text(text, encoding="utf-8")

    # Copy sidecar markdown/json manifests for traceability, but the HTML itself is standalone.
    for sidecar in src_dir.glob("*.json"):
        shutil.copy2(sidecar, out_dir / sidecar.name)
    for sidecar in src_dir.glob("*.md"):
        shutil.copy2(sidecar, out_dir / sidecar.name)

    manifest = {
        "source_html": str(src_html.resolve()),
        "output_html": str(out_html.resolve()),
        "embedded_asset_count": len(assets),
        "missing_asset_refs": missing,
        "source_html_bytes": src_html.stat().st_size,
        "source_asset_bytes": sum((src_dir / ref).stat().st_size for ref in assets),
        "output_html_bytes": out_html.stat().st_size,
        "mode": "base64-json-once-plus-loader",
    }
    (out_dir / "embedded_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
