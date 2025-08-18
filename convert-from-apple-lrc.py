from pathlib import Path
from xml.etree import ElementTree as ET
import json, re, sys

def coerce_to_ttml_string(path: Path) -> str:
    """
    Accepts either:
      1) a raw TTML file (starts with <tt ...)
      2) a snippet like: "ttml": "<tt ...</tt>"
      3) a JSON object that contains a 'ttml' field
    """
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    if raw.lstrip().startswith("<tt"):
        return raw
    candidate = raw
    if not candidate.lstrip().startswith("{"):
        candidate = "{\n" + candidate.rstrip(", \n") + "\n}"
    data = json.loads(candidate)
    return data["ttml"]

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

def convert_ttml_to_elrc(input_path: Path, output_path: Path, subtract_itunes_offset: bool=True):
    ns = {
        "tt": "http://www.w3.org/ns/ttml",
        "itunes": "http://music.apple.com/lyric-ttml-internal",
        "ttm": "http://www.w3.org/ns/ttml#metadata",
    }

    ttml_xml = coerce_to_ttml_string(input_path)
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
    out_lines.append("[re:TTML→Enhanced LRC]")
    if dur_sec is not None:
        out_lines.append(f"[length:{fmt_lrc_time(dur_sec)}]")
    out_lines.append("[offset:0]")  # we bake the offset into timestamps

    def apply_offset(t):
        return t - offset_sec if subtract_itunes_offset else t + offset_sec

    for p in root.findall(".//tt:body//tt:p", ns):
        p_begin = p.attrib.get("begin")
        p_begin_sec = parse_time_to_seconds(p_begin) if p_begin else None

        tokens = []
        first_span_sec = None
        for span in p.findall(".//tt:span", ns):
            sb = span.attrib.get("begin")
            sb_sec = parse_time_to_seconds(sb) if sb else (p_begin_sec or 0.0)
            if first_span_sec is None:
                first_span_sec = sb_sec
            adj_sec = apply_offset(sb_sec)
            word = (span.text or "").strip()
            if word:
                tokens.append(f"<{fmt_lrc_time(adj_sec)}>{word}")

        if not tokens:
            continue

        line_time_sec = p_begin_sec if p_begin_sec is not None else (first_span_sec or 0.0)
        line_time_adj = apply_offset(line_time_sec)
        out_lines.append(f"[{fmt_lrc_time(line_time_adj)}] " + " ".join(tokens))

    output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

if __name__ == "__main__":
    # Usage:
    #   python ttml_to_elrc.py /path/to/input.xml /path/to/output.lrc
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sample.xml")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output_enhanced.lrc")
    convert_ttml_to_elrc(in_path, out_path)
    print("Wrote", out_path)
