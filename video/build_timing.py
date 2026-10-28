"""Erzeugt video/timing.js aus den Aufnahmen in video/aufnahmen/.

Für jede Aufnahme liegt in aufnahmen/transkripte/<name>.json ein Whisper-Transkript
mit Wortzeiten ({"duration", "words": [{"w", "s", "e"}]}). Daraus werden Szenenlängen
und Satzzeiten berechnet, damit die Animationen zum gesprochenen Text passen.
timing.js wird von animation.html (Bildzeiten) und assemble.py (Ton und Kamera) gelesen.
"""
import html
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REC = HERE / "aufnahmen"

GAP = 0.6  # Pause zwischen zwei Aufnahmen in einer Szene

# Pro Szene: lead = Vorlauf vor der ersten Aufnahme, tail = Nachlauf.
# lines: pro Drehbuchzeile die Aufnahme(n), None = (noch) nicht aufgenommen.
# cam: Kamera-Clips, die nacheinander laufen; "lines" = welche Zeilen darin gesprochen werden.
PLAN = [
    {"lead": 5.5, "tail": 0.3, "cam": [{"src": "szene1_intro.mov", "lines": [0, 1, 2]}]},
    {"lead": 1.2, "tail": 1.0, "lines": [["szene2_A1.m4a"], ["szene2_A2.m4a"], ["szene2_A3.m4a"]]},
    {"lead": 1.0, "tail": 1.0, "lines": [["szene3_B1.m4a"], ["szene3_B2.m4a"], ["szene3_B3.m4a"], ["szene3_B4.m4a"], ["szene3_B5.m4a"]]},
    {"lead": 1.0, "tail": 1.0, "lines": [["szene4_C1.m4a"], ["szene4_C2.m4a"], ["szene4_C3.m4a"]]},
    {"lead": 1.0, "tail": 1.2, "lines": [["szene5_A1.m4a"], ["szene5_C1a.m4a", "szene5_C1b.m4a"], ["szene5_C2.m4a"]]},
    {"lead": 0.0, "tail": 4.5, "cam": [{"src": "szene6_outro.mov", "lines": [0, 1]}, {"src": "szene6_danke.mov", "lines": [2]}]},
]
NAMES = ["Jojo", "Maxi", "Maximilian"]  # von links nach rechts im Bild
NAME_X = [420, 1000, 1560]  # wo die drei im Intro-Video stehen (Bildmitte der Person, bei 1920 px Breite)
CREDITS = [" · ".join(NAMES), "Quelle: Wikipedia, Artikel „Antibiotikum“"]


def script_lines():
    """Die Sprecherzeilen pro Szene aus index.html (Drehbuch)."""
    src = (HERE.parent / "index.html").read_text(encoding="utf-8")
    scenes = []
    for sec in re.findall(r'<section class="block" id="s\d">(.*?)</section>', src, re.S):
        scenes.append([html.unescape(t) for t in re.findall(r'<div class="row [ABC]"><span class="who">[ABC]</span><p>(.*?)</p>', sec)])
    return scenes


def sentences(text):
    return re.split(r"(?<=[.!?])\s+", text.strip())


def nwords(text):
    return len(text.split())


def silence_bounds(path, dur):
    """Erste und letzte hörbare Stelle laut ffmpeg silencedetect."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a", "-af",
                          "silencedetect=noise=-38dB:d=0.25", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
    first, last = 0.0, dur
    if starts and starts[0] < 0.05 and ends:
        first = ends[0]
    if len(starts) > len(ends) or (starts and ends and ends[-1] >= dur - 0.05 and starts[-1] > first):
        last = starts[-1]
    return first, last


def clip(src, cam=False):
    tr = json.loads((REC / "transkripte" / (Path(src).stem + ".json")).read_text(encoding="utf-8"))
    dur, words = tr["duration"], tr["words"]
    if cam:
        a, b = max(0.0, words[0]["s"] - 0.35), min(dur, words[-1]["e"] + 0.45)
    else:
        f, l = silence_bounds(REC / src, dur)
        a, b = max(0.0, f - 0.12), min(dur, max(l, words[-1]["e"]) + 0.3)
    ws = [{"w": w["w"].strip(), "s": max(0.0, w["s"] - a), "e": max(0.0, w["e"] - a)} for w in words if w["e"] > a]
    return {"src": src, "in": round(a, 3), "out": round(b, 3), "len": round(b - a, 3), "words": ws}


def map_sentences(texts, words, offset):
    """Satzanfänge/-enden der Drehbuchsätze auf die Wortzeiten der Aufnahme abbilden.

    Stimmt die Zahl der Sätze im Transkript, gelten dessen Satzgrenzen;
    sonst wird über den Anteil an der Wortzahl zugeordnet.
    """
    sents = [s for t in texts for s in sentences(t)]
    ends = [i for i, w in enumerate(words) if re.search(r"[.!?]$", w["w"])]
    if ends and ends[-1] != len(words) - 1:
        ends.append(len(words) - 1)
    if len(ends) == len(sents):
        starts = [0] + [e + 1 for e in ends[:-1]]
        spans = list(zip(starts, ends))
    else:
        total, acc, spans = sum(nwords(s) for s in sents), 0, []
        for s in sents:
            i0 = min(len(words) - 1, round(acc / total * len(words)))
            acc += nwords(s)
            i1 = max(i0, min(len(words) - 1, round(acc / total * len(words)) - 1))
            spans.append((i0, i1))
    out = [[round(offset + words[i0]["s"], 3), round(offset + words[i1]["e"], 3)] for i0, i1 in spans]
    # in Zeilen gruppieren
    res, k = [], 0
    for t in texts:
        n = len(sentences(t))
        res.append(out[k:k + n])
        k += n
    return res


def main():
    script = script_lines()
    scenes, audio, video = [], [], []
    start = 0.0
    for si, plan in enumerate(PLAN):
        texts = script[si]
        lines = [None] * len(texts)
        t = plan["lead"]
        if "cam" in plan:
            cams = []
            for c in plan["cam"]:
                cl = clip(c["src"], cam=True)
                sents = map_sentences([texts[i] for i in c["lines"]], cl["words"], t)
                for i, ss in zip(c["lines"], sents):
                    lines[i] = {"t0": ss[0][0], "t1": ss[-1][1], "sents": ss}
                cams.append({"src": c["src"], "in": cl["in"], "out": cl["out"], "at": round(start + t, 3)})
                video.append(cams[-1])
                t += cl["len"]
        else:
            first = True
            for i, srcs in enumerate(plan["lines"]):
                if srcs is None:
                    continue
                if not first:
                    t += GAP
                first = False
                words, line_start = [], t
                for j, src in enumerate(srcs):
                    if j:
                        t += 0.35
                    cl = clip(src)
                    words += [{"w": w["w"], "s": w["s"] + t - line_start, "e": w["e"] + t - line_start} for w in cl["words"]]
                    audio.append({"src": src, "in": cl["in"], "out": cl["out"], "at": round(start + t, 3)})
                    t += cl["len"]
                ss = map_sentences([texts[i]], words, line_start)[0]
                lines[i] = {"t0": ss[0][0], "t1": ss[-1][1], "sents": ss,
                            "words": [[w["w"], round(line_start + w["s"], 3)] for w in words]}
        dur = round(t + plan["tail"], 3)
        scenes.append({"dur": dur, "lead": plan["lead"], "tail": plan["tail"], "lines": lines})
        start += dur
    intro = video[0]
    names = {"names": NAMES, "x": NAME_X, "from": round(intro["at"] + 1.0, 3), "to": round(intro["at"] + intro["out"] - intro["in"] - 0.2, 3)}
    data = {"duration": round(start, 3), "scenes": scenes, "audio": audio, "video": video, "credits": CREDITS, "names": names}
    (HERE / "timing.js").write_text("// Erzeugt von build_timing.py – nicht von Hand ändern.\nwindow.TIMING = "
                                    + json.dumps(data, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    print(f"timing.js geschrieben: {start:.1f} s")
    for i, s in enumerate(scenes):
        print(f"  Szene {i + 1}: {s['dur']:.1f} s" + ("  (fehlende Zeilen: " + ", ".join(str(k + 1) for k, l in enumerate(s["lines"]) if l is None) + ")" if None in s["lines"] else ""))


if __name__ == "__main__":
    main()
