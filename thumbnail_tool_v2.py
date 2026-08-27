from __future__ import annotations
import os, subprocess, tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication,QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QMessageBox,QProgressBar,QPushButton,QSpinBox,QVBoxLayout,QWidget
from video_tools import VIDEO_EXTENSIONS, find_ffmpeg
VIDEO_FILTER="Video's (*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.ts *.mts *.m2ts *.wmv *.flv *.mpeg *.mpg);;Alle bestanden (*)"
class ThumbnailToolWindow(QDialog):
 def __init__(self,parent:QWidget|None=None):
  super().__init__(parent); self.setWindowTitle("VideoAudioScanner - Thumbnail Tool"); self.resize(1040,740); self.selected_files=[]; self._preview_pixmap=None; self._build_ui(); self._apply_theme()
 def _build_ui(self):
  root=QVBoxLayout(self); root.setContentsMargins(24,22,24,22); root.setSpacing(14); h=QHBoxLayout(); b=QVBoxLayout(); t=QLabel("THUMBNAIL TOOL"); t.setObjectName("title"); b.addWidget(t); s=QLabel("Maak één of meerdere thumbnails uit video's. Het originele videobestand blijft volledig onaangetast."); s.setObjectName("subtitle"); s.setWordWrap(True); b.addWidget(s); h.addLayout(b,1); self.count_label=QLabel("0 video's geselecteerd"); self.count_label.setObjectName("count"); h.addWidget(self.count_label,alignment=Qt.AlignmentFlag.AlignTop); root.addLayout(h)
  content=QHBoxLayout(); left=QVBoxLayout(); panel=QWidget(); panel.setObjectName("panel"); l=QVBoxLayout(panel); st=QLabel("1. Video's kiezen"); st.setObjectName("panelTitle"); l.addWidget(st); r=QHBoxLayout(); q=QPushButton("Video's kiezen…"); q.clicked.connect(self.choose_files); r.addWidget(q); q=QPushButton("Map kiezen…"); q.clicked.connect(self.choose_folder); r.addWidget(q); q=QPushButton("Selectie wissen"); q.clicked.connect(self.clear_selection); r.addWidget(q); r.addStretch(); l.addLayout(r); self.file_list=QLabel("Nog geen video's geselecteerd."); self.file_list.setObjectName("fileList"); self.file_list.setWordWrap(True); l.addWidget(self.file_list); left.addWidget(panel)
  panel=QWidget(); panel.setObjectName("panel"); f=QFormLayout(panel); self.second=QSpinBox(); self.second.setRange(0,86400); self.second.setValue(5); self.second.setSuffix(" sec"); f.addRow("Moment:",self.second); self.format=QComboBox(); self.format.addItem("JPG - compact","jpg"); self.format.addItem("PNG - maximale kwaliteit","png"); self.format.currentIndexChanged.connect(self._format_changed); f.addRow("Afbeelding:",self.format); self.quality=QSpinBox(); self.quality.setRange(1,31); self.quality.setValue(2); f.addRow("JPG kwaliteit:",self.quality); self.width=QSpinBox(); self.width.setRange(0,7680); self.width.setValue(0); self.width.setSuffix(" px"); f.addRow("Breedte:",self.width); rr=QHBoxLayout(); self.output=QLineEdit(); self.output.setPlaceholderText("Doelmap voor thumbnails"); rr.addWidget(self.output,1); q=QPushButton("Bladeren…"); q.clicked.connect(self.choose_output); rr.addWidget(q); f.addRow("Doelmap:",rr); left.addWidget(panel); left.addStretch(); content.addLayout(left,1)
  panel=QWidget(); panel.setObjectName("panel"); l=QVBoxLayout(panel); t=QLabel("2. Voorbeeld"); t.setObjectName("panelTitle"); l.addWidget(t); self.preview=QLabel("Kies een video en klik op\n‘Voorbeeld maken’."); self.preview.setObjectName("preview"); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMinimumSize(440,320); l.addWidget(self.preview,1); self.preview_name=QLabel(""); self.preview_name.setObjectName("previewName"); self.preview_name.setWordWrap(True); l.addWidget(self.preview_name); q=QPushButton("Voorbeeld maken"); q.setObjectName("secondary"); q.clicked.connect(self.make_preview); l.addWidget(q); content.addWidget(panel,1); root.addLayout(content,1)
  self.progress=QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); self.progress.setFormat("Klaar"); root.addWidget(self.progress); r=QHBoxLayout(); self.status=QLabel("Klaar."); r.addWidget(self.status,1); q=QPushButton("Sluiten"); q.clicked.connect(self.reject); r.addWidget(q); q=QPushButton("Thumbnails maken"); q.setObjectName("primary"); q.clicked.connect(self.generate_thumbnails); r.addWidget(q); root.addLayout(r)
 def _apply_theme(self):
  self.setStyleSheet("QDialog{background:#101216;color:#e8eaed;} QLabel#title{color:#fff;font-size:30px;font-weight:900;} QLabel#subtitle{color:#8f96a3;font-size:14px;} QLabel#count{color:#b9c8dc;background:#182235;border:1px solid #315f9e;border-radius:7px;padding:8px 12px;} QWidget#panel{background:#171a20;border:1px solid #303640;border-radius:10px;} QLabel#panelTitle{color:#fff;font-size:17px;font-weight:800;} QLabel#fileList{color:#9da5b2;background:#12151a;border:1px solid #282d35;border-radius:7px;padding:10px;} QLabel#preview{color:#737c89;background:#0c0f13;border:1px dashed #3b424d;border-radius:7px;} QLabel#previewName{color:#9da5b2;} QLineEdit,QComboBox,QSpinBox{background:#1e2127;border:1px solid #353a43;border-radius:6px;padding:7px;color:#e8eaed;} QPushButton{background:#292e36;border:1px solid #3c424c;border-radius:7px;padding:9px 14px;color:#e8eaed;font-weight:600;} QPushButton:hover{background:#353b45;} QPushButton#primary{background:#315f9e;color:#fff;} QPushButton#secondary{background:#26384f;color:#fff;} QProgressBar{background:#171a20;border:1px solid #303640;border-radius:6px;text-align:center;color:#e8eaed;min-height:18px;}")
 @staticmethod
 def _creationflags(): return subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
 def _format_changed(self): self.quality.setEnabled(self.format.currentData()=="jpg")
 def choose_files(self):
  p,_=QFileDialog.getOpenFileNames(self,"Kies video's","",VIDEO_FILTER)
  if p:self._set_files(p)
 def choose_folder(self):
  d=QFileDialog.getExistingDirectory(self,"Kies videomap")
  if not d:return
  try:p=[str(x) for x in sorted(Path(d).iterdir()) if x.is_file() and x.suffix.lower() in VIDEO_EXTENSIONS]
  except OSError as e:QMessageBox.critical(self,"Thumbnail Tool",str(e));return
  if not p:QMessageBox.information(self,"Thumbnail Tool","Geen ondersteunde video's in deze map gevonden.");return
  self._set_files(p)
 def _set_files(self,paths):
  out=[];seen=set()
  for p in paths:
   try:n=str(Path(p).resolve())
   except OSError:continue
   if n not in seen and Path(n).is_file():seen.add(n);out.append(n)
  self.selected_files=out; self._refresh_file_list()
  if out and not self.output.text().strip():self.output.setText(str(Path(out[0]).parent))
  self.make_preview()
 def _refresh_file_list(self):
  n=len(self.selected_files); self.count_label.setText(f"{n:,} {'video' if n==1 else 'video\'s'} geselecteerd")
  lines=[Path(p).name for p in self.selected_files[:10]]
  if n>10:lines.append(f"… en nog {n-10:,} video's")
  self.file_list.setText("\n".join(lines) if lines else "Nog geen video's geselecteerd.")
 def clear_selection(self):
  self.selected_files=[]; self._refresh_file_list(); self.preview.clear(); self.preview.setText("Kies een video en klik op\n‘Voorbeeld maken’."); self.preview_name.clear(); self._preview_pixmap=None; self.status.setText("Selectie gewist.")
 def choose_output(self):
  d=QFileDialog.getExistingDirectory(self,"Kies doelmap")
  if d:self.output.setText(d)
 def _run_ffmpeg(self,source,target):
  ff=find_ffmpeg()
  if not ff:return False,"FFmpeg kon niet worden gevonden."
  cmd=[ff,"-hide_banner","-loglevel","error","-i",source,"-ss",str(self.second.value()),"-map","0:v:0","-frames:v","1"]
  if self.width.value()>0:cmd += ["-vf",f"scale={self.width.value()}:-2"]
  cmd += (["-q:v",str(self.quality.value())] if self.format.currentData()=="jpg" else ["-compression_level","6"])+["-y",target]
  try:r=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",creationflags=self._creationflags())
  except OSError as e:return False,str(e)
  if r.returncode:return False,r.stderr.strip() or "FFmpeg gaf een onbekende fout."
  try:ok=Path(target).is_file() and Path(target).stat().st_size>0
  except OSError:ok=False
  return (True,"") if ok else (False,"FFmpeg heeft geen geldige afbeelding aangemaakt.")
 def make_preview(self):
  if not self.selected_files:self.preview.setText("Kies eerst minstens één video.");return
  source=self.selected_files[0]; suffix=".jpg" if self.format.currentData()=="jpg" else ".png"; d=Path(tempfile.gettempdir())/"VideoAudioScanner"
  try:d.mkdir(parents=True,exist_ok=True)
  except OSError as e:self.preview.setText("Voorbeeld kon niet worden voorbereid.");self.preview_name.setText(str(e));return
  target=d/f"thumbnail_preview{suffix}"; self.status.setText(f"Voorbeeld maken: {Path(source).name}"); self.progress.setFormat("Voorbeeld maken…"); QApplication.processEvents(); ok,error=self._run_ffmpeg(source,str(target))
  if not ok:self.preview.clear();self.preview.setText("Voorbeeld kon niet worden gemaakt.");self.preview_name.setText(error);self.status.setText("Voorbeeld mislukt.");return
  pix=QPixmap(str(target))
  if pix.isNull():self.preview.setText("Afbeelding kon niet worden geladen.");return
  self._preview_pixmap=pix;self._show_preview_pixmap();self.preview_name.setText(f"Voorbeeld: {Path(source).name} • {self.second.value()} sec • {pix.width()}×{pix.height()} px");self.status.setText("Voorbeeld klaar. Pas het moment aan en maak opnieuw een voorbeeld voor een ander frame.");self.progress.setValue(100);self.progress.setFormat("Voorbeeld klaar")
 def _show_preview_pixmap(self):
  if self._preview_pixmap:self.preview.setPixmap(self._preview_pixmap.scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
 def resizeEvent(self,e):super().resizeEvent(e);self._show_preview_pixmap()
 @staticmethod
 def _unique_target(folder,stem,suffix):
  p=folder/f"{stem}_thumbnail{suffix}";i=2
  while p.exists():p=folder/f"{stem}_thumbnail_{i}{suffix}";i+=1
  return p
 def generate_thumbnails(self):
  if not self.selected_files:QMessageBox.warning(self,"Thumbnail Tool","Kies eerst één of meerdere video's.");return
  out=Path(self.output.text().strip()) if self.output.text().strip() else Path(self.selected_files[0]).parent
  try:out.mkdir(parents=True,exist_ok=True)
  except OSError as e:QMessageBox.critical(self,"Thumbnail Tool",f"Doelmap kon niet worden aangemaakt.\n\n{e}");return
  suffix=".jpg" if self.format.currentData()=="jpg" else ".png";total=len(self.selected_files);okn=[];bad=[]
  for i,src in enumerate(self.selected_files,1):
   self.status.setText(f"Thumbnail {i}/{total}: {Path(src).name}");self.progress.setFormat(f"{i}/{total} • {Path(src).name}");QApplication.processEvents();target=self._unique_target(out,Path(src).stem,suffix);ok,error=self._run_ffmpeg(src,str(target));(okn if ok else bad).append(target if ok else (src,error));self.progress.setValue(int(i*100/total));QApplication.processEvents()
  if not bad:QMessageBox.information(self,"Thumbnail Tool",f"Klaar.\n\n{len(okn):,} thumbnail(s) gemaakt.\n\nDoelmap:\n{out}");return
  lines=[f"Gelukt: {len(okn):,}",f"Mislukt: {len(bad):,}",""]
  for src,error in bad[:8]:lines += [Path(src).name,error,""]
  if len(bad)>8:lines.append(f"… en nog {len(bad)-8:,} fouten.")
  QMessageBox.warning(self,"Thumbnail Tool","\n".join(lines))

def main():
 app=QApplication.instance();own=app is None
 if own:app=QApplication([])
 w=ThumbnailToolWindow();w.show();return app.exec() if own else 0
if __name__=="__main__":raise SystemExit(main())
