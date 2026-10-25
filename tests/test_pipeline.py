"""Small regression checks for data/voice consistency and Chinese caption wrapping."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from render_video import timed_audio, wrap
from build_summary import build


class PipelineTests(unittest.TestCase):
    def test_measured_sentence_timing_and_stale_narration(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, frames in [('a', 8000), ('b', 16000)]:
                with wave.open(str(root / f'{name}.wav'), 'wb') as wav:
                    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                    wav.writeframes(bytes(frames*2))
            manifest = {'narration': '甲。乙。', 'segments': [
                {'text': '甲。', 'audio': 'a.wav'}, {'text': '乙。', 'audio': 'b.wav'}]}
            (root/'timing.json').write_text(json.dumps(manifest), encoding='utf-8')
            scene = {'id': 's01', 'narration': '甲。乙。', 'timing': 'timing.json'}
            audio, duration, cues = timed_audio(scene, root, root/'merged.wav')
            self.assertEqual(duration, 3)
            self.assertEqual(cues, [(0, 1, '甲。'), (1, 3, '乙。')])
            with wave.open(str(audio)) as wav:
                self.assertEqual(wav.getnframes(), 24000)
            scene['narration'] = '甲。丙。'
            with self.assertRaisesRegex(ValueError, 'regenerate speech'):
                timed_audio(scene, root, root/'merged.wav')

    def test_sentence_transcript_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'timing.json').write_text(json.dumps({'narration':'甲。','segments':[{'text':'乙。','audio':'missing.wav'}]}),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'transcript does not match'):
                timed_audio({'id':'s01','narration':'甲。','timing':'timing.json'},root,root/'merged.wav')

    def test_caption_does_not_start_with_closing_punctuation(self):
        class Font:
            def getlength(self, text): return len(text)
        lines = wrap('甲乙丙丁。下一句。', Font(), 4)
        self.assertEqual(''.join(lines), '甲乙丙丁。下一句。')
        self.assertTrue(all(len(line) <= 4 and not line.startswith('。') for line in lines))

    def test_summary_preserves_text_and_escapes_tex(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            data=dict(title='总结',original_title='A & B_1',authors='作者',publication='2026',url='https://example.org',scope='摘要',abstract='只读摘要。',keywords=['术语'],reference='来源',sections=[{'title':'结论','blocks':['提高5%，未报告其他结果。[1]']}])
            path=root/'summary.json';path.write_text(json.dumps(data),encoding='utf-8')
            build(path)
            md=(root/'summary.md').read_text(encoding='utf-8')
            tex=(root/'summary.tex').read_text(encoding='utf-8')
            self.assertIn('提高5%',md);self.assertIn(r'提高5\%',tex)
            self.assertIn(r'A \& B\_1',tex);self.assertIn(r'\cite{source}',tex)


if __name__ == '__main__':
    unittest.main()
