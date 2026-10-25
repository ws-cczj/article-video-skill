"""Render reviewed storyboards with measured sentence timing. Requires Pillow/FFmpeg.

Adapted from the user's local paper-to-video renderer; self-contained in this skill.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 1280, 720
BG, PANEL, INK, MUTED, ACCENT = '#091e2b', '#153747', '#f2f6f3', '#acc4ca', '#66dfca'


def wrap(text, font, width):
    lines, line = [], ''
    for char in text:
        if char == '\n':
            lines.append(line)
            line = ''
        elif font.getlength(line + char) > width:
            if char in '，。！？；：、）】》”’.,!?;:)]' and line:
                # Keep closing punctuation with its preceding character.
                lines.append(line[:-1])
                line = line[-1] + char
            else:
                lines.append(line)
                line = char
        else:
            line += char
    if line:
        lines.append(line)
    if len(lines) == 2 and '\n' not in text and font.getlength(lines[-1]) < width*0.25:
        joined = ''.join(lines)
        valid = [i for i in range(1, len(joined))
                 if joined[i] not in '，。！？；：、）】》”’.,!?;:)]'
                 and max(font.getlength(joined[:i]), font.getlength(joined[i:])) <= width]
        if valid:
            split = min(valid, key=lambda i: abs(font.getlength(joined[:i])-font.getlength(joined[i:])))
            lines = [joined[:split], joined[split:]]
    return lines


def block(draw, text, xy, font, width, max_lines, fill=INK):
    lines = wrap(text, font, width)
    if len(lines) > max_lines:
        raise ValueError(f'Text too long for layout; split scene: {text[:60]}')
    step = int(font.size * 1.4)
    for i, line in enumerate(lines):
        draw.text((xy[0], xy[1] + i * step), line, font=font, fill=fill)


def cues(text, duration):
    # Punctuation-aware chunks, approximate timing proportional to character count.
    chunks, current = [], ''
    for char in text:
        current += char
        if len(current) >= 32 or char in '。！？!?；;\n':
            if current.strip():
                chunks.append(current.strip())
            current = ''
    if current.strip():
        chunks.append(current.strip())
    total = sum(map(len, chunks))
    result, start = [], 0.0
    for chunk in chunks:
        end = start + duration * len(chunk) / total
        result.append((start, end, chunk))
        start = end
    return result


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def timed_audio(scene, root, destination):
    manifest = json.loads((root / scene['timing']).read_text(encoding='utf-8-sig'))
    if manifest['narration'] != scene['narration']:
        raise ValueError(f'{scene["id"]}: narration changed; regenerate speech')
    segments = manifest['segments']
    compact = lambda s: re.sub(r'\s+', '', s)
    if compact(''.join(s['text'] for s in segments)) != compact(scene['narration']):
        raise ValueError(f'{scene["id"]}: audio transcript does not match narration')
    chunks, subtitles, total, params = [], [], 0.0, None
    for segment in segments:
        with wave.open(str(root / segment['audio']), 'rb') as wav:
            current = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
            if params and current != params:
                raise ValueError('Sentence WAV formats must match')
            params = current
            length = wav.getnframes() / wav.getframerate()
            if length <= 0:
                raise ValueError('Empty speech segment')
            chunks.append(wav.readframes(wav.getnframes()))
            subtitles.append((total, total+length, segment['text']))
            total += length
    if not chunks:
        raise ValueError('No speech segments')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), 'wb') as wav:
        wav.setnchannels(params[0]); wav.setsampwidth(params[1]); wav.setframerate(params[2])
        for chunk in chunks:
            wav.writeframes(chunk)
    return destination, total, subtitles


def frame(scene, index, count, reveal, caption, fonts, picture):
    im = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(im)
    small, body, title, subtitle = fonts
    draw.text((52, 25), f'文献精读  /  {scene.get("chapter", "研究讲解")}    {index+1:02} / {count:02}', font=small, fill=ACCENT)
    block(draw, scene['title'], (52, 65), title, 1170, 1)
    block(draw, scene['objective'], (54, 130), body, 1160, 2, MUTED)
    if picture is not None:
        fitted = ImageOps.contain(picture, (1168, 340))
        im.paste(fitted, ((W-fitted.width)//2, 190+(340-fitted.height)//2))
    elif scene['kind'] == 'bars':
        bars, maximum = scene['bars'], scene['maximum']
        x0, width = 365, 700
        draw.line((x0, 202, x0, 510), fill=MUTED, width=1)
        for k in range(5):
            x = x0 + width*k/4
            draw.line((x, 202, x, 510), fill='#244550', width=1)
            draw.text((x-10, 178), f'{maximum*k/4:g}', font=small, fill=MUTED)
        for j, entry in enumerate(bars):
            y = 220 + j*56
            block(draw, entry['label'], (62, y), body, 290, 1)
            if j < reveal:
                color = ACCENT if entry.get('highlight') else '#638998'
                end = x0 + width*entry['value']/maximum
                draw.rounded_rectangle((x0, y+3, max(x0+2,end), y+32), radius=4, fill=color)
                draw.text((end+10, y), entry.get('display', str(entry['value'])), font=small, fill=INK)
    else:
        items = scene['items']
        n = len(items)
        gap = 32 if scene['kind'] == 'flow' else 20
        cw = (1168 - gap * (n-1)) // n
        for i, item in enumerate(items):
            x = 56 + i * (cw + gap)
            active = i < reveal
            draw.rounded_rectangle((x, 230, x+cw, 490), radius=18,
                                   fill=PANEL if active else '#15243a',
                                   outline=ACCENT if active else '#314158', width=2)
            draw.text((x+20, 250), f'{i+1:02}', font=body, fill=ACCENT if active else MUTED)
            if active:
                block(draw, item, (x+20, 310), body, cw-40, 4)
            if scene['kind'] == 'flow' and i < n-1:
                mid = x+cw+gap//2
                draw.line((x+cw+3, 360, mid+6, 360), fill=ACCENT, width=3)
                draw.polygon([(mid+9, 360), (mid, 354), (mid, 366)], fill=ACCENT)
    block(draw, scene['source'], (54, 548), small, 1165, 1, MUTED)
    draw.rounded_rectangle((40, 591, 1240, 696), radius=12, fill='#080f1c')
    block(draw, caption, (66, 608), subtitle, 1145, 2)
    draw.rectangle((0, H-5, int(W*(index+1)/count), H), fill=ACCENT)
    return im


def render(args):
    source = Path(args.storyboard).resolve()
    root = source.parent
    story = json.loads(source.read_text(encoding='utf-8-sig'))
    scenes = story.get('scenes', [])
    if not scenes:
        raise ValueError('Storyboard has no scenes')
    ffmpeg = shutil.which(args.ffmpeg)
    if not ffmpeg:
        raise ValueError('FFmpeg unavailable; supply --ffmpeg')
    candidates = [args.font, os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts/msyh.ttc'),
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/System/Library/Fonts/PingFang.ttc']
    font = next((p for p in candidates if p and Path(p).is_file()), None)
    if not font:
        raise ValueError('Supply a CJK font via --font')
    fonts = [ImageFont.truetype(font, size) for size in (21, 30, 44, 30)]
    output = Path(args.output).resolve()
    if output.suffix.lower() != '.mp4':
        raise ValueError('Output must be an .mp4 file')
    output.parent.mkdir(parents=True, exist_ok=True)
    previews = output.parent / (output.stem + '-frames')
    previews.mkdir(exist_ok=True)
    plans, seen = [], set()
    # Validate everything before spending time encoding.
    for i, scene in enumerate(scenes):
        sid = scene.get('id', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', sid) or sid in seen:
            raise ValueError('Scene IDs must be unique safe identifiers')
        seen.add(sid)
        for key in ('title', 'objective', 'narration', 'source'):
            if not isinstance(scene.get(key), str) or not scene[key].strip():
                raise ValueError(f'{sid}: missing {key}')
        kind = scene.get('kind')
        picture = None
        if kind == 'image':
            with Image.open(root / scene['image']) as original:
                picture = original.convert('RGB')
            n = 1
        elif kind == 'bars':
            n = len(scene.get('bars', []))
            maximum = scene.get('maximum', 0)
            if not 1 <= n <= 5 or not math.isfinite(maximum) or maximum <= 0:
                raise ValueError(f'{sid}: invalid bar chart')
            for bar in scene['bars']:
                if not math.isfinite(bar['value']) or not 0 <= bar['value'] <= maximum:
                    raise ValueError(f'{sid}: bar exceeds axis')
        elif kind in ('flow', 'compare', 'concept'):
            items = scene.get('items', [])
            n = len(items)
            if not 1 <= n <= 4 or (kind == 'compare' and n != 2):
                raise ValueError(f'{sid}: invalid item count')
            if any(not isinstance(x, str) or not x.strip() for x in items):
                raise ValueError(f'{sid}: items must be nonempty strings')
        else:
            raise ValueError(f'{sid}: unsupported kind {kind}')
        audio = None
        voice_length = 0
        subtitles = None
        if not args.silent:
            if scene.get('timing'):
                audio, voice_length, subtitles = timed_audio(scene, root, root / 'audio' / f'{sid}.wav')
            elif not scene.get('audio'):
                raise ValueError(f'{sid}: missing audio; use --silent only for previews')
            else:
                audio = (root / scene['audio']).resolve()
                with wave.open(str(audio), 'rb') as wav:
                    voice_length = wav.getnframes() / wav.getframerate()
            if voice_length <= 0:
                raise ValueError(f'{sid}: empty audio')
        minimum = float(scene.get('duration', 0))
        if not math.isfinite(minimum) or minimum < 0:
            raise ValueError(f'{sid}: duration must be finite and nonnegative')
        seconds = max(minimum, voice_length+0.5 if audio else max(3, len(scene['narration'])/4))
        frames = math.ceil(seconds * args.fps)
        seconds = frames / args.fps
        if subtitles is None:
            subtitles = cues(scene['narration'], voice_length if audio else seconds)
        # Keep the last caption during the small audio tail.
        subtitles[-1] = (subtitles[-1][0], seconds, subtitles[-1][2])
        full = frame(scene, i, len(scenes), n, subtitles[-1][2], fonts, picture)
        # Check every subtitle, not only the representative frame.
        for _, _, caption in subtitles:
            block(ImageDraw.Draw(full), caption, (66, 608), fonts[-1], 1145, 2)
        full = frame(scene, i, len(scenes), n, subtitles[-1][2], fonts, picture)
        full.save(previews / f'{sid}.png')
        plans.append((scene, n, picture, audio, seconds, frames, subtitles))
    srt, offset, timeline = [], 0.0, []
    with tempfile.TemporaryDirectory(prefix='paper-video-') as temp:
        parts = []
        for i, (scene, n, picture, audio, seconds, frames, subtitles) in enumerate(plans):
            part = Path(temp) / f'{i:04}.mp4'
            command = [ffmpeg, '-y', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                       '-video_size', f'{W}x{H}', '-framerate', str(args.fps), '-i', 'pipe:0']
            if audio:
                command += ['-i', str(audio), '-af', 'apad', '-c:a', 'aac', '-ar', '48000', '-ac', '2']
            command += ['-t', str(seconds), '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', '22', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(part)]
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors, stdout=subprocess.DEVNULL)
                try:
                    cached, previous = None, None
                    for f in range(frames):
                        t = f / args.fps
                        caption = next((c for a, b, c in subtitles if a <= t < b), subtitles[-1][2])
                        if scene.get('reveal_at'):
                            reveal = min(n, sum(t >= when for when in scene['reveal_at']))
                        else:
                            reveal = min(n, 1+int(t/max(0.01, seconds*0.55/n)))
                        key = (reveal, caption)
                        if key != previous:
                            cached = frame(scene, i, len(scenes), reveal, caption, fonts, picture).tobytes()
                            previous = key
                        process.stdin.write(cached)
                    process.stdin.close()
                    code = process.wait()
                    if code:
                        errors.seek(0)
                        raise RuntimeError(errors.read().decode('utf-8', errors='replace'))
                except BaseException:
                    process.kill()
                    process.wait()
                    errors.seek(0)
                    detail = errors.read().decode('utf-8', errors='replace')
                    if detail:
                        print(detail)
                    raise
            parts.append(part)
            for a, b, caption in subtitles:
                srt.append(f'{len(srt)+1}\n{timestamp(offset+a)} --> {timestamp(offset+b)}\n{caption}\n')
            timeline.append({'id': scene['id'], 'start': offset, 'end': offset+seconds,
                             'title': scene['title'], 'source': scene['source'],
                             'subtitle_timing': 'measured sentences' if scene.get('timing') else 'estimated'})
            offset += seconds
            print(f'Rendered {scene["id"]}: {seconds:.2f}s', flush=True)
        listing = Path(temp) / 'concat.txt'
        listing.write_text('\n'.join(f"file '{p.name}'" for p in parts), encoding='utf-8')
        subprocess.run([ffmpeg, '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
                        '-c', 'copy', '-movflags', '+faststart', str(output)], check=True)
    output.with_suffix('.srt').write_text('\n'.join(srt), encoding='utf-8')
    output.with_suffix('.timeline.json').write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'video': str(output), 'seconds': offset, 'audio': not args.silent}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('storyboard')
    parser.add_argument('--output', default='explainer.mp4')
    parser.add_argument('--font')
    parser.add_argument('--ffmpeg', default='ffmpeg')
    parser.add_argument('--fps', type=int, default=15, choices=range(1, 121))
    parser.add_argument('--silent', action='store_true')
    render(parser.parse_args())
