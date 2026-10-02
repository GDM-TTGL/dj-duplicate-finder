import shutil, subprocess, tempfile, threading, unittest, wave
from pathlib import Path
import numpy as np
from core import scan, quarantine, restore, Cancelled, extract_features, similarity

class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        (self.root/'a.mp3').write_bytes(b'audio fixture')
        (self.root/'b.mp3').write_bytes(b'audio fixture')
    def tearDown(self): self.tmp.cleanup()
    def test_move_restore_and_exclusion(self):
        report=scan(self.root,False); self.assertEqual(len(report.matches),1)
        journal=quarantine(report,{self.root/'b.mp3'})
        self.assertTrue((self.root/'a.mp3').exists()); self.assertFalse((self.root/'b.mp3').exists())
        self.assertEqual(len(scan(self.root,False).files),1)
        self.assertEqual(restore(journal),1); self.assertEqual(restore(journal),0)
    def test_cannot_move_both(self):
        with self.assertRaises(ValueError): quarantine(scan(self.root,False),{self.root/'a.mp3',self.root/'b.mp3'})
    def test_changed_selected(self):
        report=scan(self.root,False); (self.root/'b.mp3').write_bytes(b'changed')
        with self.assertRaises(ValueError): quarantine(report,{self.root/'b.mp3'})
        self.assertFalse((self.root/'_DJ_DUPLICADOS').exists())
    def test_changed_retained(self):
        report=scan(self.root,False); (self.root/'a.mp3').write_bytes(b'changed')
        with self.assertRaises(ValueError): quarantine(report,{self.root/'b.mp3'})
    def test_restore_never_overwrites(self):
        journal=quarantine(scan(self.root,False),{self.root/'b.mp3'})
        (self.root/'b.mp3').write_bytes(b'new file')
        with self.assertRaises(ValueError): restore(journal)
        self.assertEqual((self.root/'b.mp3').read_bytes(),b'new file')
    def test_modified_quarantine(self):
        journal=quarantine(scan(self.root,False),{self.root/'b.mp3'})
        (journal.parent/'archivos'/'b.mp3').write_bytes(b'changed')
        with self.assertRaises(ValueError): restore(journal)
    def test_cancel(self):
        event=threading.Event(); event.set()
        with self.assertRaises(Cancelled): scan(self.root,False,event=event)
    def test_silent_not_probable(self):
        f=extract_features(np.zeros(11025*12,dtype='<i2').tobytes())
        self.assertEqual(similarity(f,f),0)
    def test_symlink_ignored(self):
        try: (self.root/'link.mp3').symlink_to(self.root/'a.mp3')
        except OSError: self.skipTest('Symlink unavailable')
        self.assertEqual(len(scan(self.root,False).files),2)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class AudioTests(unittest.TestCase):
    def test_bitrate_metadata_versions_and_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); sr=44100; t=np.arange(sr*16)/sr
            # Changing musical notes and harmonics, with rhythms; no static tone fixture.
            notes=np.array([220,330,262,392,294,440,247,349])
            freq=notes[(t*2).astype(int)%len(notes)]
            signal=(.25*np.sin(2*np.pi*np.cumsum(freq)/sr)+.10*np.sin(2*np.pi*np.cumsum(freq*2)/sr))*(.65+.35*np.sin(2*np.pi*3*t)**2)
            def wav(name,s):
                with wave.open(str(root/name),'wb') as f:
                    f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr); f.writeframes((s*32767).astype('<i2').tobytes())
            wav('song.wav',signal)
            wav('different.wav',.3*np.random.default_rng(7).normal(0,.4,len(t)))
            def encode(name,args):
                subprocess.run(['ffmpeg','-v','error','-y','-i',str(root/'song.wav'),*args,str(root/name)],check=True)
            encode('song_128.mp3',['-b:a','128k'])
            encode('song_extended.mp3',['-b:a','320k','-metadata','title=Song Extended'])
            encode('song.mp4',['-c:a','aac','-b:a','192k'])
            # MP4 with actual image, sharing audio with the other media.
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=160x120:r=10','-i',str(root/'song.wav'),'-t','16','-c:v','mpeg4','-c:a','aac','-b:a','192k',str(root/'video.mp4')],check=True)
            report=scan(root)
            self.assertFalse(report.errors,report.errors)
            pairs=[m for m in report.matches if {m.a.path.name,m.b.path.name}=={'song_128.mp3','song_extended.mp3'}]
            self.assertEqual(len(pairs),1); self.assertIn('Versiones distintas',pairs[0].kind)
            self.assertEqual(pairs[0].keep.name,'song_extended.mp3')
            self.assertTrue(any('Audio de video' in m.kind for m in report.matches))
            self.assertFalse(any('different.wav' in (m.a.path.name,m.b.path.name) for m in report.matches))

if __name__=='__main__': unittest.main()
