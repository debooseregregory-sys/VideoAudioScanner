from __future__ import annotations

# UI refinement only: keep the working frame-extraction/grid engine unchanged.
# This file intentionally keeps the existing ThumbnailWorker implementation
# and only presents the simplified final controls requested by the user.

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QObject
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget
from video_tools import VIDEO_EXTENSIONS, find_ffmpeg

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

VIDEO_FILTER = "Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"

class ThumbnailWorker:
    CELL_W, CELL_H = 480, 270
    def __init__(self, source, target, image_format, quality, width, mode, tasks=None, screenshot_count=20, columns=5):
        self.source=source; self.target=target; self.image_format=image_format; self.quality=quality; self.width=width; self.mode=mode; self.tasks=tasks or []
        self.screenshot_count=max(1,int(screenshot_count)); self.columns=max(1,int(columns)); self.stop_event=threading.Event(); self.process=None
    def request_stop(self):
        self.stop_event.set()
        if self.process:
            try:self.process.terminate()
            except OSError:pass
    def _creationflags(self): return subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    def _run(self,cmd,target=None):
        if self.stop_event.is_set():return False,'Gestopt door gebruiker.'
        try:
            self.process=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=self._creationflags());_,err=self.process.communicate()
        except OSError as exc:self.process=None;return False,str(exc)
        p=self.process;self.process=None
        if self.stop_event.is_set():
            if target:
                try:Path(target).unlink(missing_ok=True)
                except OSError:pass
            return False,'Gestopt door gebruiker.'
        if p.returncode!=0:return False,(err or 'FFmpeg gaf een onbekende fout.').strip()
        if target and (not Path(target).is_file() or Path(target).stat().st_size==0):return False,'FFmpeg heeft geen geldige afbeelding aangemaakt.'
        return True,''
    def _ffprobe(self):
        ff=find_ffmpeg()
        if not ff:return None
        candidate=Path(ff).with_name('ffprobe.exe' if os.name=='nt' else 'ffprobe')
        return str(candidate) if candidate.exists() else shutil.which('ffprobe')
    def _duration(self,source):
        probe=self._ffprobe()
        if not probe:return None,'FFprobe kon niet worden gevonden naast FFmpeg.'
        try:
            r=subprocess.run([probe,'-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=self._creationflags(),check=False)
            if r.returncode!=0:return None,(r.stderr or 'FFprobe gaf een fout.').strip()
            d=float(r.stdout.strip());return (d,'') if d>0 else (None,'De videolengte kon niet worden bepaald.')
        except (OSError,ValueError) as exc:return None,str(exc)
    def _extract_frame(self,ffmpeg,source,timestamp,path):
        cmd=[ffmpeg,'-hide_banner','-loglevel','error','-ss',f'{timestamp:.3f}','-i',source,'-frames:v','1','-vf',f'scale={self.CELL_W}:{self.CELL_H}:force_original_aspect_ratio=decrease,pad={self.CELL_W}:{self.CELL_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1','-q:v','2','-y',str(path)]
        return self._run(cmd,path)
    def _make_grid(self,source,target):
        if not PIL_AVAILABLE:return False,'Pillow ontbreekt. Installeer met: python -m pip install Pillow'
        ff=find_ffmpeg()
        if not ff:return False,'FFmpeg kon niet worden gevonden.'
        duration,error=self._duration(source)
        if duration is None:return False,error
        count=self.screenshot_count; cols=min(self.columns,count); rows=(count+cols-1)//cols
        timestamps=[duration*(i+0.5)/count for i in range(count)]
        temp=Path(tempfile.mkdtemp(prefix='vas_thumb_'));frames=[]
        try:
            for i,t in enumerate(timestamps):
                if self.stop_event.is_set():return False,'Gestopt door gebruiker.'
                p=temp/f'frame_{i:03d}.jpg';ok,err=self._extract_frame(ff,source,t,p)
                if not ok:return False,f'Screenshot {i+1}/{count} mislukt: {err}'
                frames.append(p)
            sheet=Image.new('RGB',(cols*self.CELL_W,rows*self.CELL_H),'black')
            for i,p in enumerate(frames):
                with Image.open(p) as im:sheet.paste(im.convert('RGB'),((i%cols)*self.CELL_W,(i//cols)*self.CELL_H))
            if self.width>0 and sheet.width!=self.width:sheet=sheet.resize((self.width,max(1,round(sheet.height*self.width/sheet.width))),Image.Resampling.LANCZOS)
            out=Path(target);out.parent.mkdir(parents=True,exist_ok=True)
            if self.image_format=='jpg':sheet.save(out,'JPEG',quality=max(1,min(100,100-(self.quality-1)*3)),optimize=True)
            else:sheet.save(out,'PNG',compress_level=6)
            sheet.close();return True,''
        except Exception as exc:return False,f'Raster maken mislukt: {exc}'
        finally:
            for p in frames:
                try:p.unlink(missing_ok=True)
                except OSError:pass
            try:temp.rmdir()
            except OSError:pass
    def run(self,s):
        if self.mode=='preview':
            ok,err=self._make_grid(self.source,self.target);s.finished.emit('preview',ok,self.target,err,self.screenshot_count if ok else 0,self.screenshot_count);return
        total=len(self.tasks)
        for i,(src,target) in enumerate(self.tasks,1):
            if self.stop_event.is_set():break
            ok,err=self._make_grid(src,target);s.progress.emit(i,total,Path(src).name,ok,err)
        s.finished.emit('batch',not self.stop_event.is_set(),'','',0,total)

class _WorkerSignals(QObject):
    progress=Signal(int,int,str,bool,str);finished=Signal(str,bool,str,str,int,int)
class ThumbnailThread(QThread):
    progress=Signal(int,int,str,bool,str);result=Signal(str,bool,str,str,int,int)
    def __init__(self,w,parent=None):super().__init__(parent);self.worker=w
    def run(self):
        s=_WorkerSignals();s.progress.connect(self.progress.emit);s.finished.connect(self.result.emit);self.worker.run(s)

class ThumbnailToolWindow(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('VideoAudioScanner - Thumbnail Tool');self.resize(1080,780);self.selected_files=[];self._preview_pixmap=None;self._thread=None;self._worker=None;self._busy=False;self._batch_success=0;self._batch_failed=[];self._build_ui();self._apply_theme()
    def _spin(self,value,minimum,maximum,suffix=''):
        s=QSpinBox();s.setRange(minimum,maximum);s.setValue(value);s.setSuffix(suffix);s.setKeyboardTracking(False);return s
    def _build_ui(self):
        root=QVBoxLayout(self);root.setContentsMargins(24,22,24,22);root.setSpacing(14)
        head=QHBoxLayout();box=QVBoxLayout();t=QLabel('THUMBNAIL TOOL');t.setObjectName('title');box.addWidget(t);sub=QLabel('Maak automatisch één samengesteld raster met screenshots verspreid over de volledige video.');sub.setObjectName('subtitle');sub.setWordWrap(True);box.addWidget(sub);head.addLayout(box,1);self.count_label=QLabel("0 video's geselecteerd");self.count_label.setObjectName('count');head.addWidget(self.count_label,alignment=Qt.AlignmentFlag.AlignTop);root.addLayout(head)
        content=QHBoxLayout();content.setSpacing(14);left=QVBoxLayout();left.setSpacing(12)
        panel=QWidget();panel.setObjectName('panel');pl=QVBoxLayout(panel);pl.setContentsMargins(16,14,16,14);pt=QLabel("1. Video's kiezen");pt.setObjectName('panelTitle');pl.addWidget(pt);buttons=QHBoxLayout()
        for text,fn in [("Video's kiezen…",self.choose_files),("Map kiezen…",self.choose_folder),("Selectie wissen",self.clear_selection)]:b=QPushButton(text);b.clicked.connect(fn);buttons.addWidget(b)
        buttons.addStretch();pl.addLayout(buttons);self.file_list=QLabel('Nog geen video\'s geselecteerd.');self.file_list.setObjectName('fileList');self.file_list.setWordWrap(True);self.file_list.setMinimumHeight(110);pl.addWidget(self.file_list);left.addWidget(panel)
        settings=QWidget();settings.setObjectName('panel');form=QFormLayout(settings);form.setContentsMargins(16,14,16,14);form.setVerticalSpacing(11)
        self.screenshot_count=self._spin(20,1,100,' stuks');self.screenshot_count.setToolTip('Aantal screenshots; automatisch gelijkmatig verdeeld over de volledige video.');form.addRow('Screenshots:',self.screenshot_count)
        self.columns=self._spin(5,1,20,' kolommen');self.columns.setToolTip('Aantal kolommen in het raster.');form.addRow('Kolommen:',self.columns)
        self.format=QComboBox();self.format.addItem('JPG - compact','jpg');self.format.addItem('PNG - maximale kwaliteit','png');self.format.currentIndexChanged.connect(self._format_changed);form.addRow('Afbeelding:',self.format)
        self.quality=self._spin(2,1,31);form.addRow('JPG kwaliteit:',self.quality)
        self.width=self._spin(0,0,7680,' px');self.width.setToolTip('0 = automatische rasterbreedte.');form.addRow('Rasterbreedte:',self.width)
        row=QHBoxLayout();self.output=QLineEdit();self.output.setPlaceholderText('Doelmap voor rasters');row.addWidget(self.output,1);b=QPushButton('Bladeren…');b.clicked.connect(self.choose_output);row.addWidget(b);form.addRow('Doelmap:',row);left.addWidget(settings);left.addStretch();content.addLayout(left,1)
        preview=QWidget();preview.setObjectName('panel');pv=QVBoxLayout(preview);pv.setContentsMargins(16,14,16,14);pt=QLabel('2. Voorbeeld raster');pt.setObjectName('panelTitle');pv.addWidget(pt);self.preview=QLabel('Kies een video en klik op\n‘Voorbeeld maken’.');self.preview.setObjectName('preview');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumSize(470,350);pv.addWidget(self.preview,1);self.preview_name=QLabel('');self.preview_name.setObjectName('previewName');self.preview_name.setWordWrap(True);pv.addWidget(self.preview_name);self.preview_button=QPushButton('Voorbeeld maken');self.preview_button.setObjectName('secondary');self.preview_button.clicked.connect(self.make_preview);pv.addWidget(self.preview_button);content.addWidget(preview,1);root.addLayout(content,1)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setValue(0);self.progress.setFormat('Klaar');root.addWidget(self.progress);bottom=QHBoxLayout();self.status=QLabel('Klaar.');self.status.setObjectName('status');bottom.addWidget(self.status,1);self.close_button=QPushButton('Sluiten');self.close_button.clicked.connect(self.reject);bottom.addWidget(self.close_button);self.cancel_button=QPushButton('Stoppen');self.cancel_button.setObjectName('cancel');self.cancel_button.setVisible(False);self.cancel_button.clicked.connect(self.cancel_operation);bottom.addWidget(self.cancel_button);self.generate_button=QPushButton('Rasters maken');self.generate_button.setObjectName('primary');self.generate_button.clicked.connect(self.generate_thumbnails);bottom.addWidget(self.generate_button);root.addLayout(bottom)
    def _apply_theme(self):
        self.setStyleSheet('''QDialog{background:#101216;color:#fff} QLabel{color:#fff} QLabel#title{color:#fff;font-size:30px;font-weight:900} QLabel#subtitle{color:#fff;font-size:14px} QLabel#count{color:#fff;background:#182235;border:1px solid #315f9e;border-radius:7px;padding:8px 12px} QWidget#panel{background:#171a20;border:1px solid #303640;border-radius:10px} QLabel#panelTitle{color:#fff;font-size:17px;font-weight:800} QLabel#fileList{color:#fff;background:#12151a;border:1px solid #282d35;border-radius:7px;padding:10px} QLabel#preview{color:#fff;background:#0c0f13;border:1px dashed #3b424d;border-radius:7px} QLabel#previewName{color:#fff} QLabel#status{color:#fff} QLineEdit,QComboBox,QSpinBox{background:#1e2127;border:1px solid #353a43;border-radius:6px;padding:7px;color:#fff} QComboBox QAbstractItemView{background:#1e2127;color:#fff;selection-background-color:#315f9e} QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;color:#fff;font-weight:600} QPushButton:hover{background:#353b45} QPushButton#primary{background:#315f9e;border-color:#4679bd} QPushButton#secondary{background:#26384f;border-color:#3d638e} QPushButton#cancel{background:#653636;border-color:#8b4a4a} QProgressBar{background:#171a20;border:1px solid #303640;border-radius:6px;text-align:center;color:#fff;min-height:18px} QProgressBar::chunk{background:#315f9e;border-radius:5px} QToolTip{background:#1e2127;color:#fff;border:1px solid #4a515d;padding:5px}''')
    def _format_changed(self):self.quality.setEnabled(self.format.currentData()=='jpg')
    def _set_busy(self,busy):
        self._busy=busy
        for c in (self.preview_button,self.generate_button,self.close_button):c.setEnabled(not busy)
        self.cancel_button.setVisible(busy);self.cancel_button.setEnabled(busy)
    def choose_files(self):
        if self._busy:return
        paths,_=QFileDialog.getOpenFileNames(self,"Kies video's",'',VIDEO_FILTER)
        if paths:self._set_files(paths)
    def choose_folder(self):
        if self._busy:return
        folder=QFileDialog.getExistingDirectory(self,'Kies videomap')
        if not folder:return
        try:paths=[str(p) for p in sorted(Path(folder).iterdir()) if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        except OSError as exc:QMessageBox.critical(self,'Thumbnail Tool',f'De videomap kon niet worden gelezen.\n\n{exc}');return
        self._set_files(paths)
    def _set_files(self,paths):
        self.selected_files=list(dict.fromkeys(paths));self.count_label.setText(f"{len(self.selected_files)} video's geselecteerd");names=[Path(p).name for p in self.selected_files];self.file_list.setText('\n'.join(names[:12])+((f'\n… en {len(names)-12} meer.' if len(names)>12 else '')));self.status.setText('Selectie bijgewerkt.')
    def clear_selection(self):self.selected_files=[];self.count_label.setText("0 video's geselecteerd");self.file_list.setText("Nog geen video's geselecteerd.");self.preview.clear();self.preview_name.clear();self.status.setText('Selectie gewist.')
    def choose_output(self):
        folder=QFileDialog.getExistingDirectory(self,'Kies doelmap')
        if folder:self.output.setText(folder)
    def _output_folder(self):return self.output.text().strip() or (str(Path(self.selected_files[0]).parent/'thumbnails') if self.selected_files else '')
    def _tasks(self):
        folder=self._output_folder();Path(folder).mkdir(parents=True,exist_ok=True);ext=self.format.currentData();n=self.screenshot_count.value();cols=self.columns.value();return [(src,str(Path(folder)/(Path(src).stem+f'_grid_{n}shots_{min(cols,n)}x{(n+min(cols,n)-1)//min(cols,n)}.{ext}'))) for src in self.selected_files]
    def _start(self,w):
        self._worker=w;self._thread=ThumbnailThread(w,self);self._thread.progress.connect(self._on_progress);self._thread.result.connect(self._on_result);self._set_busy(True);self._thread.start()
    def make_preview(self):
        if self._busy:return
        if not self.selected_files:self.status.setText('Kies eerst een video.');return
        if not PIL_AVAILABLE:self.status.setText('Pillow ontbreekt. Installeer met: python -m pip install Pillow');return
        src=self.selected_files[0];ext=self.format.currentData();target=str(Path(tempfile.gettempdir())/f'thumbnail_preview.{ext}');w=ThumbnailWorker(src,target,ext,self.quality.value(),self.width.value(),'preview',screenshot_count=self.screenshot_count.value(),columns=self.columns.value());self.status.setText('Rastervoorbeeld wordt gemaakt…');self._start(w)
    def generate_thumbnails(self):
        if self._busy:return
        if not self.selected_files:QMessageBox.information(self,'Thumbnail Tool','Kies eerst minstens één video.');return
        if not PIL_AVAILABLE:QMessageBox.critical(self,'Thumbnail Tool','Pillow ontbreekt. Installeer met: python -m pip install Pillow');return
        try:tasks=self._tasks()
        except OSError as exc:QMessageBox.critical(self,'Thumbnail Tool',f'Doelmap kon niet worden aangemaakt.\n\n{exc}');return
        self._batch_success=0;self._batch_failed=[];self.progress.setRange(0,len(tasks));self.progress.setValue(0);w=ThumbnailWorker('','',self.format.currentData(),self.quality.value(),self.width.value(),'batch',tasks=tasks,screenshot_count=self.screenshot_count.value(),columns=self.columns.value());self.status.setText('Rasters worden gemaakt…');self._start(w)
    def cancel_operation(self):
        if self._worker:self._worker.request_stop();self.status.setText('Stoppen…')
    def _on_progress(self,index,total,name,ok,error):
        self.progress.setValue(index);self.progress.setFormat(f'{index}/{total}');self.status.setText(('Klaar: ' if ok else 'Fout: ')+name+(f' — {error}' if error else ''));self._batch_success+=int(ok)
        if not ok:self._batch_failed.append((name,error))
    def _on_result(self,mode,ok,target,error,done,total):
        self._set_busy(False)
        if mode=='preview':
            if ok:
                self._preview_pixmap=QPixmap(target);self._update_preview();n=self.screenshot_count.value();cols=min(self.columns.value(),n);rows=(n+cols-1)//cols;self.preview_name.setText(f'{Path(self.selected_files[0]).name} — {n} beelden — {cols} × {rows} raster');self.status.setText('Voorbeeld klaar.')
            else:self.status.setText('Voorbeeld mislukt: '+error)
        else:self.progress.setValue(total);self.status.setText(f'Klaar: {self._batch_success} raster(s) gemaakt'+(f', {len(self._batch_failed)} mislukt' if self._batch_failed else '')+'.')
    def _update_preview(self):
        if self._preview_pixmap and not self._preview_pixmap.isNull():self.preview.setPixmap(self._preview_pixmap.scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
    def resizeEvent(self,event):super().resizeEvent(event);self._update_preview()
    def reject(self):
        if self._busy:QMessageBox.information(self,'Thumbnail Tool','Stop de huidige bewerking eerst.');return
        super().reject()

def open_thumbnail_tool(parent=None):return ThumbnailToolWindow(parent)
def main():
    app=QApplication.instance() or QApplication([]);ThumbnailToolWindow().exec()
if __name__=='__main__':main()
