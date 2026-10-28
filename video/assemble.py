"""Setzt das fertige Video zusammen: gerenderte Animation + Kameraclips + Tonaufnahmen.

    node video/render.mjs --hud 0 --sub 0 --out video/animation_ohne_ton.mp4
    python3 video/assemble.py video/animation_ohne_ton.mp4 video/antibiotika_video.mp4

Zeiten und Schnittpunkte kommen aus video/timing.js (siehe build_timing.py).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "aufnahmen"

# iPhone-Videos sind HDR (HLG); ohne Umrechnung sähen sie im fertigen SDR-Video blass aus
HDR_TO_SDR = ("zscale=tin=arib-std-b67:min=bt2020nc:pin=bt2020:t=linear:npl=100,format=gbrpf32le,"
              "zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv")
VOICE = "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo"


def main(anim, out):
    src = (HERE / "timing.js").read_text(encoding="utf-8")
    timing = json.loads(src[src.index("{"):src.rindex("}") + 1])
    duration = timing["duration"]

    inputs = ["-i", str(anim)]
    vf, af, amix = [], [], []
    last = "0:v"
    for k, v in enumerate(timing["video"], start=1):
        inputs += ["-i", str(REC / v["src"])]
        at, length = v["at"], v["out"] - v["in"]
        vf.append(f"[{k}:v]trim=start={v['in']}:end={v['out']},setpts=PTS-STARTPTS+{at}/TB,"
                  f"{HDR_TO_SDR},scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
                  f"fps=30,format=yuv420p[c{k}]")
        vf.append(f"[{last}][c{k}]overlay=eof_action=pass:enable='between(t,{at},{at + length:.3f})'[v{k}]")
        last = f"v{k}"
        af.append(f"[{k}:a]atrim={v['in']}:{v['out']},asetpts=PTS-STARTPTS,{VOICE},adelay={round(at * 1000)}:all=1[a{k}]")
        amix.append(f"[a{k}]")
    base = len(timing["video"]) + 1
    for j, a in enumerate(timing["audio"]):
        n = base + j
        inputs += ["-i", str(REC / a["src"])]
        af.append(f"[{n}:a]atrim={a['in']}:{a['out']},asetpts=PTS-STARTPTS,{VOICE},adelay={round(a['at'] * 1000)}:all=1[a{n}]")
        amix.append(f"[a{n}]")
    af.append(f"{''.join(amix)}amix=inputs={len(amix)}:normalize=0:duration=longest,apad,atrim=0:{duration}[aout]")

    cmd = ["ffmpeg", "-loglevel", "error", "-stats", "-y", *inputs,
           "-filter_complex", ";".join(vf + af),
           "-map", f"[{last}]", "-map", "[aout]", "-t", str(duration),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print("Fertig:", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
