"""Photo tile for the browser: a thumbnail with a full-screen button and a copy-path button.

The tile is an in-page component (Streamlit's v2 API), not an iframe. It sizes to its
image, so the grid keeps each photo's own proportions, and it can use the page's
clipboard and full-screen APIs. Only the two buttons act: the image itself does nothing
when clicked.

Components run as trusted page code. File names and captions are set through
properties (textContent, src), never innerHTML.
"""

import base64
import io
from pathlib import Path

import streamlit.components.v2 as v2
from PIL import Image

_HTML = """
<figure class="tile">
  <div class="frame">
    <img alt="">
    <div class="actions">
      <button class="icon" type="button" data-action="fullscreen" title="Open full screen" aria-label="Open full screen">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>
      </button>
      <button class="icon" type="button" data-action="copy" title="Copy file path" aria-label="Copy file path">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
      </button>
    </div>
  </div>
  <figcaption class="caption"></figcaption>
  <div class="status" role="status"></div>
</figure>
"""

_CSS = """
.tile { margin: 0; position: relative; font: inherit; color: inherit; }
.frame { position: relative; border-radius: 6px; overflow: hidden; background: rgba(128, 128, 128, 0.12); }
img { display: block; width: 100%; height: auto; }
.actions { position: absolute; top: 6px; right: 6px; display: flex; gap: 4px; opacity: 0.6; transition: opacity 0.15s; }
.frame:hover .actions, .actions:focus-within { opacity: 1; }
.icon { width: 28px; height: 28px; padding: 0; border: none; border-radius: 50%; cursor: pointer;
        background: rgba(0, 0, 0, 0.55); color: #fff; display: inline-flex; align-items: center; justify-content: center; }
.icon:hover, .icon:focus-visible { background: rgba(0, 0, 0, 0.8); outline: 2px solid #fff; outline-offset: 1px; }
.icon svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2;
            stroke-linecap: round; stroke-linejoin: round; }
.caption { margin-top: 4px; font-size: 0.875rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; opacity: 0.85; }
.status { min-height: 1rem; font-size: 0.75rem; opacity: 0.9; }
.status.error { color: #e0523f; opacity: 1; }
.tile:fullscreen { display: flex; flex-direction: column; justify-content: center; box-sizing: border-box;
                   background: #000; color: #fff; padding: 16px; }
.tile:fullscreen .frame { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center;
                          background: none; border-radius: 0; }
.tile:fullscreen img { width: auto; height: 100%; max-width: 100%; object-fit: contain; aspect-ratio: auto !important; }
"""

_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const tile = parentElement.querySelector(".tile");
  const img = tile.querySelector("img");
  const caption = tile.querySelector(".caption");
  const status = tile.querySelector(".status");
  const copyButton = tile.querySelector('[data-action="copy"]');
  const fullscreenButton = tile.querySelector('[data-action="fullscreen"]');

  img.src = "data:image/jpeg;base64," + data.src;
  img.alt = data.caption;
  img.style.aspectRatio = `${data.width} / ${data.height}`;
  caption.textContent = data.caption;
  caption.title = data.path;

  let timer = null;
  function show(text, isError) {
    status.textContent = text;
    status.className = isError ? "status error" : "status";
    clearTimeout(timer);
    timer = setTimeout(() => { status.textContent = ""; }, isError ? 6000 : 1500);
  }

  function copyWithSelection(text) {
    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    tile.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    return copied;
  }

  copyButton.onclick = async (event) => {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(data.path);
      show("Copied path", false);
    } catch (err) {
      if (copyWithSelection(data.path)) {
        show("Copied path", false);
      } else {
        show("Copy failed: " + err.message, true);
      }
    }
  };

  fullscreenButton.onclick = async (event) => {
    event.stopPropagation();
    try {
      if (tile.matches(":fullscreen")) {
        await document.exitFullscreen();
      } else {
        await tile.requestFullscreen();
      }
    } catch (err) {
      show("Full screen failed: " + err.message, true);
    }
  };
}
"""

_TILE = v2.component("photo_tile", html=_HTML, css=_CSS, js=_JS)


def photo_tile(jpeg: bytes, path: Path, caption: str) -> None:
    """Show a JPEG thumbnail with a full-screen button and a copy-path button.

    Args:
        jpeg: JPEG bytes of the thumbnail.
        path: File path copied by the copy button, as the local path (e.g. D:\\DCIM\\file.ARW).
        caption: Text shown under the image.
    """
    with Image.open(io.BytesIO(jpeg)) as image:
        width, height = image.size  # reads the header only, no pixel decoding
    _TILE(
        data={
            "src": base64.b64encode(jpeg).decode("ascii"),
            "path": str(path),
            "caption": caption,
            "width": width,
            "height": height,
        },
        key=str(path),
        width="stretch",
        height="content",
    )
