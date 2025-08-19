r''' 
convert-from-apple-lrc.py — Convert Apple Music TTML/JSON to LRC (traditional or enhanced)

Usage:
    # Convert from a file (Apple Music JSON, a snippet containing "ttml": "<tt...>", or raw TTML)
    python .\convert-from-apple-lrc.py <input.json|xml|ttml> [output.lrc]

    # Read from clipboard (expects Apple Music JSON or a ttml snippet)
    python .\convert-from-apple-lrc.py -c [output.lrc]

Windows PowerShell notes:
- Backslashes in paths are OK. PowerShell's escape character is the backtick (`), not the backslash.
- Quote paths that contain spaces: "C:\Users\you\Music Files\sample.xml"
- You can also use forward slashes if you prefer: C:/Users/you/Music Files/sample.xml

Examples:
    python .\convert-from-apple-lrc.py "sample copy 2.xml" output_enhanced.lrc
    python .\convert-from-apple-lrc.py -c "C:\Temp\output_enhanced.lrc"

Output behavior:
- If the input indicates word timing (itunes:timing="Word" or spans per word), an enhanced LRC is produced.
- If the input indicates line timing, a traditional LRC is produced.
- Enhanced LRC lines include per-word timestamps like <mm:ss.cc>word, and a trailing end-time token is appended to capture the final word's unique end timing.
'''

from pathlib import Path
from xml.etree import ElementTree as ET
import json, re, sys, subprocess, shutil

def _deep_find_ttml_and_display(obj):
    """Recursively search for a TTML string and displayType in an Apple Music response."""
    ttml_value = None
    display_type = None

    def visit(node):
        nonlocal ttml_value, display_type
        if isinstance(node, dict):
            # capture displayType if present
            pp = node.get("playParams") or {}
            if isinstance(pp, dict) and display_type is None:
                dt = pp.get("displayType")
                if isinstance(dt, int):
                    display_type = dt

            if ttml_value is None and isinstance(node.get("ttml"), str):
                ttml_value = node["ttml"]

            # common Apple schema: { data: [ { attributes: { ttml, playParams.displayType } } ] }
            attrs = node.get("attributes")
            if isinstance(attrs, dict):
                visit(attrs)

            # traverse nested dict values
            for v in node.values():
                if ttml_value is not None and display_type is not None:
                    break
                visit(v)
        elif isinstance(node, list):
            for v in node:
                if ttml_value is not None and display_type is not None:
                    break
                visit(v)

    visit(obj)
    return ttml_value, display_type

def coerce_raw_to_ttml_input(raw: str) -> tuple[str, int | None]:
    """
    Accepts either:
      1) a raw TTML file (starts with <tt ...)
      2) a snippet like: "ttml": "<tt ...</tt>"
      3) a full Apple Music JSON object (possibly with data[])

    Returns: (ttml_xml_string, displayType or None)
    displayType: 2 = traditional (line), 3 = enhanced (word)
    """
    # Raw TTML
    if raw.lstrip().startswith("<tt"):
        return raw, None

    # Try parse as JSON first
    json_obj = None
    try:
        if raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
            json_obj = json.loads(raw)
        else:
            # likely a snippet like: "ttml": "<tt ..." (optionally with trailing comma)
            snippet = "{\n" + raw.rstrip(", \n\r\t") + "\n}"
            json_obj = json.loads(snippet)
    except Exception:
        # As a last resort, try to extract via regex
        m = re.search(r'"ttml"\s*:\s*"(.*?)"\s*(,|\}|$)', raw, flags=re.S)
        if m:
            ttml_escaped = m.group(1)
            return bytes(ttml_escaped, "utf-8").decode("unicode_escape"), None
        raise

    ttml, display_type = _deep_find_ttml_and_display(json_obj)
    if not ttml:
        raise ValueError("Unable to locate 'ttml' in the provided input")
    return ttml, display_type

def coerce_to_ttml_input(path: Path) -> tuple[str, int | None]:
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    return coerce_raw_to_ttml_input(raw)

def parse_time_to_seconds(ts: str) -> float:
    """Handles H:MM:SS.mmm, M:SS.mmm, or SS.mmm."""
    if not ts:
        return 0.0
    ts = ts.strip()
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h*3600 + m*60 + s
        elif len(parts) == 2:
            m, s = int(parts[0]), float(parts[1])
            return m*60 + s
        else:
            return float(parts[0])
    except Exception:
        cleaned = re.sub(r"[^0-9\.:]", "", ts)
        return parse_time_to_seconds(cleaned) if cleaned else 0.0

def fmt_lrc_time(seconds: float) -> str:
    """mm:ss.cc (centiseconds)."""
    if seconds < 0: seconds = 0.0
    total_centis = int(round(seconds * 100.0))
    m = total_centis // 6000
    s = (total_centis % 6000) // 100
    cs = total_centis % 100
    return f"{m:02d}:{s:02d}.{cs:02d}"

def convert_ttml_string_to_elrc(ttml_xml: str, output_path: Path, display_type_hint: int | None = None, subtract_itunes_offset: bool=True):
    ns = {
        "tt": "http://www.w3.org/ns/ttml",
        "itunes": "http://music.apple.com/lyric-ttml-internal",
        "ttm": "http://www.w3.org/ns/ttml#metadata",
    }
    root = ET.fromstring(ttml_xml)

    # Apple’s iTunes TTML often carries a global lyricOffset
    offset_sec = 0.0
    audio_el = root.find(".//itunes:audio", ns)
    if audio_el is not None and "lyricOffset" in audio_el.attrib:
        try:
            offset_sec = float(audio_el.attrib["lyricOffset"])
        except Exception:
            offset_sec = 0.0

    body = root.find(".//tt:body", ns)
    dur_sec = parse_time_to_seconds(body.attrib.get("dur")) if (body is not None and body.attrib.get("dur")) else None

    out_lines = []
    out_lines.append("[re:TTML→LRC]")
    if dur_sec is not None:
        out_lines.append(f"[length:{fmt_lrc_time(dur_sec)}]")
    out_lines.append("[offset:0]")  # we bake the offset into timestamps

    def apply_offset(t):
        return t - offset_sec if subtract_itunes_offset else t + offset_sec

    # Determine display type: prefer explicit hint; else inspect TTML's timing or content
    if display_type_hint not in (2, 3):
        # infer from tt itunes:timing attr or presence of spans
        tt_timing = root.attrib.get(f"{{{ns['itunes']}}}timing") or root.attrib.get("itunes:timing")
        if isinstance(tt_timing, str):
            display_type = 3 if tt_timing.lower().strip() == "word" else 2
        else:
            # If any p has span children, treat as enhanced
            has_spans = root.find(".//tt:body//tt:p//tt:span", ns) is not None
            display_type = 3 if has_spans else 2
    else:
        display_type = display_type_hint

    for p in root.findall(".//tt:body//tt:p", ns):
        p_begin = p.attrib.get("begin")
        p_begin_sec = parse_time_to_seconds(p_begin) if p_begin else None

        if display_type == 2:
            # Traditional line-by-line: one timestamp per p, plain text content
            line_time_sec = p_begin_sec if p_begin_sec is not None else 0.0
            line_time_adj = apply_offset(line_time_sec)
            # Gather textual content (ignore timing spans if any)
            text_content = "".join(p.itertext()).strip()
            if not text_content:
                continue
            out_lines.append(f"[{fmt_lrc_time(line_time_adj)}] {text_content}")
        else:
            # Enhanced word-by-word: preserve spaces exactly as in TTML.
            # We build the line by walking direct children and keeping .text and .tail.
            line_parts: list[str] = []
            first_span_sec = None
            last_span_end_sec = None

            # Any leading text before the first child
            if p.text:
                line_parts.append(p.text)

            for child in list(p):
                # Only timestamp spans; copy other element text as plain text
                if child.tag == f"{{{ns['tt']}}}span":
                    sb = child.attrib.get("begin")
                    se = child.attrib.get("end")
                    sb_sec = parse_time_to_seconds(sb) if sb else (p_begin_sec or 0.0)
                    if first_span_sec is None:
                        first_span_sec = sb_sec
                    if se:
                        last_span_end_sec = parse_time_to_seconds(se)

                    adj_sec = apply_offset(sb_sec)
                    token_time = fmt_lrc_time(adj_sec)
                    word_text = child.text or ""
                    # Append token with its exact text (no trimming) to preserve intra-word splits
                    line_parts.append(f"<{token_time}>{word_text}")
                else:
                    # Not a span: include its text content if any
                    if child.text:
                        line_parts.append(child.text)

                # Preserve exact spacing or punctuation after the child
                if child.tail:
                    line_parts.append(child.tail)

            # If no spans were found, fallback to traditional line output
            if first_span_sec is None:
                line_time_sec = p_begin_sec if p_begin_sec is not None else 0.0
                line_time_adj = apply_offset(line_time_sec)
                text_content = "".join(p.itertext()).strip()
                if text_content:
                    out_lines.append(f"[{fmt_lrc_time(line_time_adj)}] {text_content}")
                continue

            # Base timestamp for the line
            line_time_sec = p_begin_sec if p_begin_sec is not None else first_span_sec
            line_time_adj = apply_offset(line_time_sec)

            # Append a trailing end-time token for the last word/line end if available
            # Prefer the last span's end; otherwise fall back to p's end
            p_end_attr = p.attrib.get("end")
            if last_span_end_sec is None and p_end_attr:
                try:
                    last_span_end_sec = parse_time_to_seconds(p_end_attr)
                except Exception:
                    last_span_end_sec = None

            if last_span_end_sec is not None:
                end_adj = apply_offset(last_span_end_sec)
                line_parts.append(f"<{fmt_lrc_time(end_adj)}>")

            out_lines.append(f"[{fmt_lrc_time(line_time_adj)}] " + "".join(line_parts))

    output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

def convert_ttml_to_elrc(input_path: Path, output_path: Path, subtract_itunes_offset: bool=True):
    ttml_xml, display_type_hint = coerce_to_ttml_input(input_path)
    convert_ttml_string_to_elrc(ttml_xml, output_path, display_type_hint, subtract_itunes_offset=subtract_itunes_offset)

def _read_clipboard_text() -> str:
    """Return current clipboard text. Prefers PowerShell on Windows; falls back to Tk, pbpaste, or xclip."""
    # Prefer PowerShell Get-Clipboard on Windows
    try:
        # -Raw to preserve newlines exactly
        completed = subprocess.run([
            "powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"
        ], check=True, capture_output=True, text=True, encoding="utf-8")
        return completed.stdout
    except Exception:
        pass
    # Fallback to tkinter
    try:
        import tkinter as tk  # type: ignore
        r = tk.Tk()
        r.withdraw()
        data = r.clipboard_get()
        r.destroy()
        return data
    except Exception:
        pass
    # macOS pbpaste
    if shutil.which("pbpaste"):
        try:
            completed = subprocess.run(["pbpaste"], check=True, capture_output=True, text=True, encoding="utf-8")
            return completed.stdout
        except Exception:
            pass
    # Linux xclip
    if shutil.which("xclip"):
        try:
            completed = subprocess.run(["xclip", "-o", "-selection", "clipboard"], check=True, capture_output=True, text=True, encoding="utf-8")
            return completed.stdout
        except Exception:
            pass
    raise RuntimeError("Unable to read clipboard text on this system.")

if __name__ == "__main__":
    # Usage:
    #   python convert-from-apple-lrc.py <input.json|xml|ttml> [output.lrc]
    #   python convert-from-apple-lrc.py -c [output.lrc]       # read from clipboard
    args = sys.argv[1:]
    if args and args[0] in ("-c", "--clipboard"):
        raw = _read_clipboard_text()
        ttml_xml, dt_hint = coerce_raw_to_ttml_input(raw.strip())
        default_out = "output_enhanced.lrc" if dt_hint == 3 else "output_traditional.lrc" if dt_hint == 2 else "output_enhanced.lrc"
        out_path = Path(args[1]) if len(args) > 1 else Path(default_out)
        convert_ttml_string_to_elrc(ttml_xml, out_path, dt_hint)
        print("Wrote", out_path)
    else:
        in_path = Path(args[0]) if args else Path("sample.xml")
        # Default output name hints based on inferred type
        try:
            _, dt_hint = coerce_to_ttml_input(in_path)
        except Exception:
            dt_hint = None
        default_out = "output_enhanced.lrc" if dt_hint == 3 else "output_traditional.lrc" if dt_hint == 2 else "output_enhanced.lrc"
        out_path = Path(args[1]) if len(args) > 1 else Path(default_out)
        convert_ttml_to_elrc(in_path, out_path)
        print("Wrote", out_path)
