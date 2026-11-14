"""Thumbnail with a copy-path overlay: clicking the image or its icon copies the file path.

Streamlit's st.image cannot run JavaScript or draw an overlay, so each thumbnail is
rendered as a small HTML component. The file path goes to the clipboard with the
browser's clipboard API, falling back to a text selection copy. If both fail, the
message under the image says so.
"""

import base64
import html
import json
from pathlib import Path

import streamlit.components.v1 as components

IFRAME_HEIGHT = 320  # pixels: image box, caption and status line
COPY_ICON = (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>'
)

_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body {{ margin: 0; font-family: "Source Sans Pro", sans-serif; font-size: 14px; color: #31333f; }}
  .wrap {{ position: relative; height: 260px; display: flex; align-items: center; justify-content: center;
          background: #f0f2f6; border-radius: 6px; cursor: copy; }}
  img {{ max-width: 100%; max-height: 260px; object-fit: contain; border-radius: 6px; display: block; }}
  .btn {{ position: absolute; top: 6px; right: 6px; width: 28px; height: 28px; padding: 0; border: none;
         border-radius: 50%; background: rgba(0, 0, 0, 0.55); color: #fff; cursor: pointer;
         display: flex; align-items: center; justify-content: center; }}
  .btn:hover {{ background: rgba(0, 0, 0, 0.8); }}
  .cap {{ margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .msg {{ font-size: 12px; min-height: 16px; color: #0a7d33; }}
  .err {{ color: #c0392b; }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #fafafa; }} .wrap {{ background: #262730; }} .msg {{ color: #5dd58a; }}
  }}
</style></head>
<body>
<div class="wrap" id="wrap" title="Click to copy the file path">
  <img src="data:image/jpeg;base64,{image}" alt="{alt}">
  <button class="btn" id="btn" title="Copy file path" aria-label="Copy file path">{icon}</button>
</div>
<div class="cap" title="{alt}">{caption}</div>
<div class="msg" id="msg"></div>
<script>
  const PATH = {path};
  const msg = document.getElementById("msg");
  let timer = null;

  function show(text, isError) {{
    msg.textContent = text;
    msg.className = isError ? "msg err" : "msg";
    clearTimeout(timer);
    timer = setTimeout(() => {{ msg.textContent = ""; }}, isError ? 6000 : 1500);
  }}

  function copyWithSelection() {{
    const field = document.createElement("textarea");
    field.value = PATH;
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    return copied;
  }}

  async function copyPath() {{
    try {{
      await navigator.clipboard.writeText(PATH);
      show("Copied path", false);
    }} catch (err) {{
      if (copyWithSelection()) {{
        show("Copied path", false);
      }} else {{
        show("Copy failed: " + err.message, true);
      }}
    }}
  }}

  document.getElementById("wrap").addEventListener("click", copyPath);
</script>
</body></html>
"""


def copyable_image(jpeg: bytes, path: Path, caption: str) -> None:
    """Show a JPEG thumbnail; clicking it or its icon copies `path` to the clipboard.

    Args:
        jpeg: JPEG bytes of the thumbnail.
        path: File path to copy. Written as the local path, e.g. D:\\DCIM\\file.ARW.
        caption: Text shown under the image (escaped before display).
    """
    encoded = base64.b64encode(jpeg).decode("ascii")
    page = _TEMPLATE.format(
        image=encoded,
        alt=html.escape(caption, quote=True),
        caption=html.escape(caption),
        icon=COPY_ICON,
        path=json.dumps(str(path)).replace("</", "<\\/"),
    )
    components.html(page, height=IFRAME_HEIGHT)
