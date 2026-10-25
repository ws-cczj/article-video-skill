"""Observable media-quality invariants: smooth edges and a continuous PCM timeline."""
from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest
import wave
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audio_master import assemble_pcm,build_master
import shutil
import json


class AudioMasterTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
    def test_silent_clip_does_not_pass_infinite_loudness_to_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with wave.open(str(root/'silent.wav'),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(bytes(4800*2))
            build_master([(root/'silent.wav',.2)],root/'master.wav','ffmpeg')
            with wave.open(str(root/'master.wav'),'rb') as wav:self.assertEqual(wav.getnframes(),9600)
            report=json.loads((root/'master.json').read_text(encoding='utf-8'))
            self.assertIn('passthrough',report['normalization'])

    def test_audio_has_exact_scene_length_and_silent_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ['one','two']:
                with wave.open(str(root/f'{name}.wav'),'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000)
                    wav.writeframes(np.full(480,1000,dtype='<i2').tobytes())
            seconds=assemble_pcm([(root/'one.wav',.1),(root/'two.wav',.1)],root/'master.wav')
            self.assertAlmostEqual(seconds,.2)
            with wave.open(str(root/'master.wav'),'rb') as wav:
                self.assertEqual(wav.getnframes(),9600)
                data=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2')
            self.assertTrue(np.all(data[480:4800]==0))
            self.assertEqual(data[0],0);self.assertEqual(data[4800],0)

    def test_audio_cannot_be_silently_truncated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with wave.open(str(root/'source.wav'),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(bytes(4800*2))
            with self.assertRaises(ValueError):assemble_pcm([(root/'source.wav',.01)],root/'master.wav')


@unittest.skipUnless(importlib.util.find_spec('skia') and Path('C:/Windows/Fonts/msyh.ttc').exists(),'Skia and test CJK font required')
class VectorQualityTests(unittest.TestCase):
    def test_diagonal_has_fractional_pixel_coverage(self):
        import skia
        from render_motion import QualityCanvas
        canvas=QualityCanvas(Path('.'),'C:/Windows/Fonts/msyh.ttc',720)
        surface=skia.Surface(40,40);c=surface.getCanvas();c.clear(skia.ColorBLACK)
        canvas.paint_object(c,dict(type='line',points=[[2.2,3.1],[36.4,27.6]],fill='#ffffff',stroke_width=1,opacity=1))
        array=surface.makeImageSnapshot().toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)
        levels=np.unique(array[:,:,0])
        self.assertGreater(sum(0<x<255 for x in levels),10)


if __name__=='__main__':unittest.main()
