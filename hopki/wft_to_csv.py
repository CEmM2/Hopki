#!/usr/bin/env python3
"""Convert Nicolet/Thermo .WFT oscilloscope waveform files to FLT-style text.

This parser follows the WFT layout described in the Nicolet WFT file-format
PDF: fixed-width ASCII header fields followed by raw binary waveform data.

Usage:
    python wft_to_csv.py input.WFT output.FLT
    python wft_to_csv.py *.WFT --out-dir converted

The output matches the legacy Nicolet/Thermo .FLT text export: a source-file
header line, a units line, then calibrated voltage/time pairs. Multi-segment
and up to three timebase zones are handled using HDELTA and the zone fields
when present.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# name, byte offset, field width
FIELDS: list[tuple[str, int, int]] = [
    ("Nic_id0", 0, 2),
    ("Niv_id1", 2, 2),
    ("Nic_id2", 4, 2),
    ("User_id", 6, 2),
    ("Header_size", 8, 12),
    ("File_size", 20, 12),
    ("File_format_version", 32, 12),
    ("Waveform_title", 44, 81),
    ("Date_year", 125, 3),
    ("Date_month", 128, 3),
    ("Date_day", 131, 3),
    ("Trigger_time_ms_since_midnight", 134, 12),
    ("Data_count", 146, 12),
    ("Vertical_zero", 158, 12),
    ("Vertical_norm", 170, 24),
    ("User_vertical_zero", 194, 24),
    ("User_vertical_norm", 218, 24),
    ("User_vertical_label", 242, 11),
    ("User_horizontal_zero", 253, 24),
    ("User_horizontal_norm", 277, 24),
    ("User_horizontal_label", 301, 11),
    ("User_notes", 312, 129),
    ("Audit", 441, 196),
    ("Nicolet_digitizer_type", 637, 21),
    ("Bytes_per_data_point", 658, 3),
    ("Resolution", 661, 3),
    ("Forward_link", 664, 81),
    ("Backward_link", 745, 81),
    ("Process_flag", 826, 3),
    ("Data_compression", 829, 3),
    ("Number_of_segments", 832, 12),
    ("Length_of_each_segment", 844, 12),
    ("Number_of_timebases", 856, 12),
    ("Length_of_zone_1", 1024, 12),
    ("Horiz_norm_zone_1", 1036, 24),
    ("Horiz_zero_zone_1", 1060, 24),
    ("Length_of_zone_2", 1084, 12),
    ("Horiz_norm_zone_2", 1096, 24),
    ("Horiz_zero_zone_2", 1120, 24),
    ("Length_of_zone_3", 1144, 12),
    ("Horiz_norm_zone_3", 1156, 24),
    ("Horiz_zero_zone_3", 1180, 24),
]


@dataclass(frozen=True)
class Zone:
    length: int
    hnorm: float
    hzero: float


@dataclass
class WFT:
    header: dict[str, str]
    raw: list[int]
    time: list[float]
    value: list[float]
    segment_index: list[int]
    point_in_segment: list[int]
    warnings: list[str]


def clean_ascii(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("latin1", errors="replace").strip()


def as_int(value: str, default: int | None = None) -> int:
    if value == "":
        if default is None:
            raise ValueError("missing required integer field")
        return default
    return int(float(value))


def as_float(value: str, default: float | None = None) -> float:
    if value == "":
        if default is None:
            raise ValueError("missing required float field")
        return default
    return float(value)


def parse_header(blob: bytes) -> dict[str, str]:
    if len(blob) < 1538:
        raise ValueError(f"file too small to contain a standard WFT header: {len(blob)} bytes")
    return {name: clean_ascii(blob[offset:offset + width]) for name, offset, width in FIELDS}


def parse_hdelta(blob: bytes, header_size: int, n_segments: int) -> list[float]:
    """Return segment start offsets. Segment 1 has offset 0."""
    hdelta = [0.0]
    for seg in range(2, n_segments + 1):
        offset = 1536 + 24 * (seg - 2)
        if offset + 24 <= header_size - 2:
            text = clean_ascii(blob[offset:offset + 24])
            hdelta.append(as_float(text, 0.0))
        else:
            hdelta.append(0.0)
    return hdelta


def get_zones(header: dict[str, str], data_count: int, segment_length: int) -> list[Zone]:
    zones: list[Zone] = []
    for idx in (1, 2, 3):
        length = as_int(header.get(f"Length_of_zone_{idx}", ""), 0)
        hnorm = as_float(header.get(f"Horiz_norm_zone_{idx}", ""), math.nan)
        hzero = as_float(header.get(f"Horiz_zero_zone_{idx}", ""), math.nan)
        if length > 0 and not math.isnan(hnorm) and not math.isnan(hzero):
            zones.append(Zone(length=length, hnorm=hnorm, hzero=hzero))

    if zones:
        return zones

    # Fallback for files that do not populate zone fields, although most do.
    hnorm = as_float(header.get("User_horizontal_norm", ""), 1.0)
    hzero = as_float(header.get("User_horizontal_zero", ""), 0.0)
    return [Zone(length=segment_length or data_count, hnorm=hnorm, hzero=hzero)]


def unpack_raw(blob: bytes, header: dict[str, str], header_size: int, data_count: int) -> list[int]:
    bytes_per_point = as_int(header.get("Bytes_per_data_point", ""), 2)
    if bytes_per_point != 2:
        raise ValueError(f"unsupported Bytes_per_data_point={bytes_per_point}; this converter expects 2")

    compression = as_int(header.get("Data_compression", ""), 0)
    if compression != 0:
        raise ValueError(f"unsupported compressed WFT data: Data_compression={compression}")

    start = header_size
    end = start + data_count * bytes_per_point
    data = blob[start:end]
    if len(data) != data_count * bytes_per_point:
        raise ValueError(
            f"file ended early: expected {data_count * bytes_per_point} bytes of data, got {len(data)}"
        )

    cpu_type = header.get("Nic_id0", "3")
    endian = ">" if cpu_type == "2" else "<"  # 68000 is big-endian; Intel and VAX files are little-endian.
    return list(struct.unpack(f"{endian}{data_count}h", data))


def read_wft(path: Path) -> WFT:
    blob = path.read_bytes()
    header = parse_header(blob)

    header_size = as_int(header["Header_size"])
    file_size = as_int(header.get("File_size", ""), len(blob))
    data_count = as_int(header["Data_count"])
    n_segments = max(1, as_int(header.get("Number_of_segments", ""), 1))
    segment_length = as_int(header.get("Length_of_each_segment", ""), 0)
    if segment_length <= 0:
        segment_length = data_count // n_segments if n_segments else data_count

    warnings: list[str] = []
    if file_size and file_size != len(blob):
        warnings.append(f"header File_size={file_size}, actual size={len(blob)}")
    if n_segments * segment_length not in (data_count, 0):
        warnings.append(
            f"Number_of_segments * Length_of_each_segment = {n_segments * segment_length}, "
            f"but Data_count={data_count}"
        )

    raw = unpack_raw(blob, header, header_size, data_count)

    vzero = as_float(header.get("Vertical_zero", ""), 0.0)
    vnorm = as_float(header.get("Vertical_norm", ""), 1.0)
    uvzero = as_float(header.get("User_vertical_zero", ""), 0.0)
    uvnorm = as_float(header.get("User_vertical_norm", ""), 1.0)
    value = [((sample - vzero) * vnorm) * uvnorm + uvzero for sample in raw]

    uhzero = as_float(header.get("User_horizontal_zero", ""), 0.0)
    uhnorm = as_float(header.get("User_horizontal_norm", ""), 1.0)
    zones = get_zones(header, data_count, segment_length)
    hdeltas = parse_hdelta(blob, header_size, n_segments)

    time: list[float] = []
    segment_index: list[int] = []
    point_in_segment: list[int] = []
    time_origin: float | None = None

    for i in range(data_count):
        seg = min(i // segment_length, n_segments - 1) if segment_length else 0
        p = i - seg * segment_length
        zone_start = 0
        zone = zones[-1]
        zone_local_p = p
        for candidate in zones:
            if p < zone_start + candidate.length:
                zone = candidate
                zone_local_p = p - zone_start
                break
            zone_start += candidate.length
        hdelta = hdeltas[seg] if seg < len(hdeltas) else 0.0
        raw_time = (zone_local_p * zone.hnorm) + zone.hzero + hdelta
        if time_origin is None:
            # Nicolet stores zone/segment times relative to an acquisition origin,
            # while the legacy .FLT export normalizes the first emitted sample to t=0.
            time_origin = raw_time
        t = (raw_time - time_origin) * uhnorm + uhzero
        time.append(t)
        segment_index.append(seg + 1)
        point_in_segment.append(p)

    return WFT(
        header=header,
        raw=raw,
        time=time,
        value=value,
        segment_index=segment_index,
        point_in_segment=point_in_segment,
        warnings=warnings,
    )


def write_flt(wft: WFT, out_path: Path, source_name: str) -> None:
    x_label = wft.header.get("User_horizontal_label") or "s"
    y_label = wft.header.get("User_vertical_label") or "V"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"{source_name}\n")
        f.write(f"{y_label}       {x_label}\n")
        for y, t in zip(wft.value, wft.time, strict=True):
            f.write(f"{y:12.7f}\t{t:12.7f}\n")


def write_metadata(wft: WFT, out_path: Path) -> None:
    meta = {
        "header": wft.header,
        "warnings": wft.warnings,
        "sample_count": len(wft.raw),
        "time_min": min(wft.time) if wft.time else None,
        "time_max": max(wft.time) if wft.time else None,
        "value_min": min(wft.value) if wft.value else None,
        "value_max": max(wft.value) if wft.value else None,
    }
    out_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def convert_one(input_path: Path, output_path: Path | None, meta: bool) -> Path:
    wft = read_wft(input_path)
    out = output_path if output_path else input_path.with_suffix(".FLT")
    write_flt(wft, out, input_path.name)
    if meta:
        write_metadata(wft, out.with_suffix(out.suffix + ".json"))
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Nicolet .WFT waveform files to FLT-style text")
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="input .WFT file(s). With one input, you may optionally add one output FLT path.",
    )
    parser.add_argument("-o", "--output", type=Path, help="output FLT when exactly one input is given")
    parser.add_argument("--out-dir", type=Path, help="directory for batch output FLT files")
    parser.add_argument("--metadata", action="store_true", help="also write a JSON file containing parsed header fields")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.output and args.out_dir:
        parser.error("use either --output or --out-dir, not both")

    explicit_output = args.output
    inputs = args.paths

    # Convenience form: python wft_to_csv.py input.WFT output.FLT
    # For true batch conversion, use --out-dir.
    if not explicit_output and not args.out_dir and len(args.paths) == 2:
        first, second = args.paths
        if first.suffix.lower() == ".wft" and second.suffix.lower() != ".wft":
            inputs = [first]
            explicit_output = second

    if explicit_output and len(inputs) != 1:
        parser.error("a single explicit output FLT is allowed only with one input file")

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    for input_path in inputs:
        out = explicit_output
        if args.out_dir:
            out = args.out_dir / f"{input_path.stem}.FLT"
        flt_path = convert_one(input_path, out, args.metadata)
        print(f"wrote {flt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
