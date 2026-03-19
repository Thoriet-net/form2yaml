from pathlib import Path
from typing import Any, Dict, List
from app import functions

import re
import yaml

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles


from jinja2 import Environment, FileSystemLoader, StrictUndefined

# ---
# form2yaml main application
# Handles:
# - loading templates
# - rendering forms
# - processing user input
# - generating YAML output
# - snapshot management
# ---


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates"
TEMPLATES_UI = Path(__file__).resolve().parent / "templates_ui"
SNAPSHOTS_DIR = ROOT / "snapshots"

app = FastAPI()
templates = Jinja2Templates(directory=str(TEMPLATES_UI))

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


 # Scan templates directory and return available template names
def list_template_names() -> List[str]:
    names: List[str] = []
    if TEMPLATES_DIR.exists():
        for p in TEMPLATES_DIR.iterdir():
            if p.is_dir() and (p / "template.meta.yaml").exists():
                names.append(p.name)
    return sorted(names)


 # Validate template name and ensure required files exist
def assert_template_exists(template_name: str) -> Path:
    if "/" in template_name or "\\" in template_name or ".." in template_name:
        raise FileNotFoundError("Invalid template name")

    tdir = TEMPLATES_DIR / template_name
    if not tdir.exists() or not tdir.is_dir():
        raise FileNotFoundError("Template dir not found")

    if not (tdir / "template.meta.yaml").exists():
        raise FileNotFoundError("Missing template.meta.yaml")

    return tdir


 # Load template.meta.yaml and normalize structure
def load_meta(template_name: str) -> Dict[str, Any]:
    tdir = assert_template_exists(template_name)
    meta_path = tdir / "template.meta.yaml"
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Meta must be a YAML mapping at top-level.")

    data.setdefault("sections", {})
    data.setdefault("always", {})
    data.setdefault("name", template_name)

    return data


def y(val: Any) -> str:
    """
    YAML-friendly scalar without quotes.
    For our use-case we want plain scalars.
    Strips whitespace and forbids newlines.
    """
    if val is None:
        return ""
    s = str(val).strip()
    s = s.replace("\r", "").replace("\n", " ")
    return s


 # Render Jinja2 template.yaml.j2 using provided context
def render_config(template_dir: Path, ctx: Dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    env.filters["y"] = y
    env.filters["to_upper"] = functions.to_upper
    env.filters["to_lower"] = functions.to_lower
    env.filters["default_if_empty"] = functions.default_if_empty
    env.filters["trim"] = functions.trim

    tpl = env.get_template("template.yaml.j2")
    return tpl.render(**ctx)


 # Convert raw form input into proper Python types based on field definition
def _coerce_value(field_def: Dict[str, Any], raw: Any) -> Any:
    """
    Convert raw POSTed values (strings) into Python types based on meta field type.
    Minimal set: bool + int. Everything else stays as-is (string or None).
    """
    ftype = (field_def or {}).get("type")

    if raw is None:
        return None

    if isinstance(raw, str) and raw.strip() == "":
        return None

    if ftype == "bool":
        s = str(raw).strip().lower()
        return s in ("true", "on", "1", "yes")

    if ftype == "int":
        try:
            return int(str(raw).strip())
        except Exception:
            return None

    return raw


 # Sanitize snapshot filename to safe filesystem format
def sanitize_snapshot_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", (name or "").strip()).strip("_")
    return s or "snapshot"


 # Build snapshot payload stored on disk
def build_snapshot_payload(template_name: str, form: Dict[str, str]) -> Dict[str, Any]:
    device_name = (form.get("device_name") or "").strip()

    return {
        "template_name": template_name,
        "device_name": device_name,
        "form_data": form,
    }


 # Load snapshot file and validate structure
def load_snapshot(template_name: str, snapshot_name: str) -> Dict[str, Any]:
    safe_name = sanitize_snapshot_name(snapshot_name)

    path = SNAPSHOTS_DIR / template_name / f"{safe_name}.yml"

    if not path.exists():
        raise FileNotFoundError("Snapshot not found")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError("Invalid snapshot format")

    return data


 # List all snapshots for given template
def list_snapshots(template_name: str) -> List[str]:
    target_dir = SNAPSHOTS_DIR / template_name
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    names: List[str] = []
    for p in target_dir.iterdir():
        if p.is_file() and p.suffix in (".yml", ".yaml"):
            names.append(p.stem)

    return sorted(names)


 # Delete snapshot file from disk
def delete_snapshot_file(template_name: str, snapshot_name: str) -> None:
    safe_name = sanitize_snapshot_name(snapshot_name)
    path = SNAPSHOTS_DIR / template_name / f"{safe_name}.yml"

    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Snapshot not found.")

    path.unlink()


 # Parse POSTed form data into structured context for Jinja rendering
def parse_posted_form(meta: Dict[str, Any], form: Dict[str, str]) -> Dict[str, Any]:
    """
    ctx passed to Jinja:
      always: {...}
      sections: {sec_key: bool}
      <sec_key>: {field_key: value, <repeatable_key>: [ {...}, {...} ] }
      values: { "<sec_key>.<field_key>": raw_value, "device_name": raw_value, "<sec>.<rkey>.__count": "N", ... }
    """
    ctx: Dict[str, Any] = {"always": meta.get("always", {}), "sections": {}, "values": {}}

    device_name = (form.get("device_name") or "").strip()
    ctx["values"]["device_name"] = device_name

    # sections enabled
    for sec_key, sec in (meta.get("sections") or {}).items():
        default_on = bool((sec or {}).get("enabled_by_default", True))
        enabled = (form.get(f"section__{sec_key}") == "on") if f"section__{sec_key}" in form else default_on
        ctx["sections"][sec_key] = enabled

    # fields
    for sec_key, sec in (meta.get("sections") or {}).items():
        sec_obj: Dict[str, Any] = {}
        fields = (sec or {}).get("fields", {}) if isinstance(sec, dict) else {}

        for field_key in (fields or {}).keys():
            name = f"{sec_key}.{field_key}"
            raw = form.get(name, "")
            ctx["values"][name] = raw

            fdef = fields.get(field_key, {}) if isinstance(fields, dict) else {}
            val = _coerce_value(fdef if isinstance(fdef, dict) else {}, raw)
            sec_obj[field_key] = val

        ctx[sec_key] = sec_obj

    # repeatables
    for sec_key, sec in (meta.get("sections") or {}).items():
        repeatables = (sec or {}).get("repeatables", {}) if isinstance(sec, dict) else {}

        for rkey, rdef in (repeatables or {}).items():
            count_name = f"{sec_key}.{rkey}.__count"
            raw_count = form.get(count_name, "")

            min_items = int((rdef or {}).get("min_items", 0))
            max_items = int((rdef or {}).get("max_items", 50))

            try:
                count = int(raw_count) if raw_count.strip() else min_items
            except Exception:
                count = min_items

            if count < min_items:
                count = min_items
            if count > max_items:
                count = max_items

            ctx["values"][count_name] = str(count)

            items: List[Dict[str, Any]] = []
            r_fields = (rdef or {}).get("fields", {}) if isinstance(rdef, dict) else {}

            for idx in range(count):
                item: Dict[str, Any] = {}
                for fkey in (r_fields or {}).keys():
                    fname = f"{sec_key}.{rkey}.{idx}.{fkey}"
                    raw = form.get(fname, "")
                    ctx["values"][fname] = raw

                    fdef = r_fields.get(fkey, {}) if isinstance(r_fields, dict) else {}
                    val = _coerce_value(fdef if isinstance(fdef, dict) else {}, raw)
                    item[fkey] = val

                items.append(item)

            if sec_key not in ctx or not isinstance(ctx.get(sec_key), dict):
                ctx[sec_key] = {}
            ctx[sec_key][rkey] = items

    return ctx


 # Home page - list available templates
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "template_names": list_template_names()},
    )


 # Render form for selected template
@app.get("/template/{template_name}", response_class=HTMLResponse)
def template_form(request: Request, template_name: str):
    meta = load_meta(template_name)

    sections_enabled = {}
    for sec_key, sec in meta.get("sections", {}).items():
        sections_enabled[sec_key] = bool((sec or {}).get("enabled_by_default", True))

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "template_name": template_name,
            "meta": meta,
            "sections_enabled": sections_enabled,
            "preview_yaml": None,
            "error": None,
            "save_message": None,
            "snapshot_names": list_snapshots(template_name),
            "current_snapshot_name": None,
            "values": {"device_name": ""},
        },
    )


 # Render preview YAML without saving
@app.post("/template/{template_name}/preview", response_class=HTMLResponse)
async def template_preview(request: Request, template_name: str):
    meta = load_meta(template_name)
    tdir = assert_template_exists(template_name)

    formdata = await request.form()
    form: Dict[str, str] = {k: str(v) for k, v in formdata.items()}

    ctx = parse_posted_form(meta, form)

    try:
        rendered = render_config(tdir, ctx)
        error = None
    except Exception as e:
        rendered = None
        error = f"{type(e).__name__}: {e}"

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "template_name": template_name,
            "meta": meta,
            "sections_enabled": dict(ctx.get("sections", {})),
            "preview_yaml": rendered,
            "error": error,
            "save_message": None,
            "snapshot_names": list_snapshots(template_name),
            "current_snapshot_name": None,
            "values": dict(ctx.get("values", {})),
        },
    )


 # Save form data as snapshot
@app.post("/template/{template_name}/save", response_class=HTMLResponse)
async def template_save(request: Request, template_name: str):
    meta = load_meta(template_name)

    formdata = await request.form()
    form: Dict[str, str] = {k: str(v) for k, v in formdata.items()}

    device_name = (form.get("device_name") or "").strip()
    if not device_name:
        ctx = parse_posted_form(meta, form)
        return templates.TemplateResponse(
            "form.html",
            {
                "request": request,
                "template_name": template_name,
                "meta": meta,
                "sections_enabled": dict(ctx.get("sections", {})),
                "preview_yaml": None,
                "error": "Device name is required to save a snapshot.",
                "save_message": None,
                "snapshot_names": list_snapshots(template_name),
                "current_snapshot_name": None,
                "values": dict(ctx.get("values", {})),
            },
        )

    safe_name = sanitize_snapshot_name(device_name)
    target_dir = SNAPSHOTS_DIR / template_name
    target_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = target_dir / f"{safe_name}.yml"
    payload = build_snapshot_payload(template_name, form)

    snapshot_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    ctx = parse_posted_form(meta, form)

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "template_name": template_name,
            "meta": meta,
            "sections_enabled": dict(ctx.get("sections", {})),
            "preview_yaml": None,
            "error": None,
            "snapshot_names": list_snapshots(template_name),
            "current_snapshot_name": None,
            "values": dict(ctx.get("values", {})),
            "save_message": f"Snapshot saved: {template_name}/{safe_name}.yml",
        },
    )


 # Load snapshot into form
@app.get("/template/{template_name}/load/{snapshot_name}", response_class=HTMLResponse)
def template_load(request: Request, template_name: str, snapshot_name: str):
    meta = load_meta(template_name)

    try:
        snap = load_snapshot(template_name, snapshot_name)
    except Exception as e:
        return templates.TemplateResponse(
            "form.html",
            {
                "request": request,
                "template_name": template_name,
                "meta": meta,
                "sections_enabled": {},
                "preview_yaml": None,
                "error": f"Error loading snapshot: {e}",
                "save_message": None,
                "snapshot_names": list_snapshots(template_name),
                "current_snapshot_name": None,
                "values": {},
            },
        )

    form = snap.get("form_data", {})

    ctx = parse_posted_form(meta, form)

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "template_name": template_name,
            "meta": meta,
            "sections_enabled": dict(ctx.get("sections", {})),
            "preview_yaml": None,
            "error": None,
            "save_message": None,
            "current_snapshot_name": None,
            "values": dict(ctx.get("values", {})),
        },
    )


 # Delete snapshot
@app.post("/template/{template_name}/delete/{snapshot_name}", response_class=HTMLResponse)
def template_delete(request: Request, template_name: str, snapshot_name: str):
    meta = load_meta(template_name)

    try:
        delete_snapshot_file(template_name, snapshot_name)
        error = None
        save_message = f"Snapshot deleted: {template_name}/{snapshot_name}.yml"
    except Exception as e:
        error = f"Error deleting snapshot: {e}"
        save_message = None

    sections_enabled = {}
    for sec_key, sec in meta.get("sections", {}).items():
        sections_enabled[sec_key] = bool((sec or {}).get("enabled_by_default", True))

    return templates.TemplateResponse(
        "form.html",
        {
            "request": request,
            "template_name": template_name,
            "meta": meta,
            "sections_enabled": sections_enabled,
            "preview_yaml": None,
            "error": error,
            "save_message": save_message,
            "snapshot_names": list_snapshots(template_name),
            "current_snapshot_name": None,
            "values": {"device_name": ""},
        },
    )


 # Generate final YAML and return as downloadable file
@app.post("/template/{template_name}/generate")
async def template_generate(request: Request, template_name: str):
    meta = load_meta(template_name)
    tdir = assert_template_exists(template_name)

    formdata = await request.form()
    form: Dict[str, str] = {k: str(v) for k, v in formdata.items()}

    ctx = parse_posted_form(meta, form)
    rendered = render_config(tdir, ctx)

    raw_device_name = str(ctx.get("values", {}).get("device_name", "")).strip()
    base_name_source = raw_device_name or template_name
    base_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", base_name_source).strip("_") or "config"
    filename = f"{base_name}.yml"

    return Response(
        content=rendered,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )