# SPDX-License-Identifier: GPL-2.0-or-later
"""MY-2K converter, host preview and ten-slot library. Never mounts a disk."""
from pathlib import Path
import os,shutil,tempfile
from PyQt5.QtCore import Qt,QTimer,QThread,pyqtSignal,QEvent,QRectF,QPoint
from PyQt5.QtGui import QImage,QMovie,QPixmap,QPainter,QPen,QColor
from PyQt5.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QGroupBox,QPushButton,QComboBox,QListWidget,QListWidgetItem,QFileDialog,QMessageBox,QProgressDialog,QSizePolicy
from vi_al_addons.my2k.animation_codec import CrsReader,convert_animation,PreviewFramePending
from vi_al_addons.my2k.animation_library_protocol import AnimationClient,slot_name
from vi_al_addons.my2k.animation_files_protocol import AnimationFilesClient
from widgets.combo_popup import ClickComboBox

class MoviePreview(QLabel):
    def __init__(self):
        super().__init__('No animation selected')
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(180,180)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setStyleSheet('background: black; color: white;')
        self.reader=self.movie=None;self.image=None;self.index=0
        self.playback_rate=None;self.frame_fraction=0
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.advance)
    def stop(self):
        self.timer.stop()
        if self.reader:self.reader.close()
        if self.movie:self.movie.stop();self.movie.deleteLater()
        self.reader=self.movie=None;self.image=None;self.clear()
    def load(self,filename):
        self.stop()
        if Path(filename).suffix.lower()in('.crs','.anm','.sml','.bkg','.sts','.aux'):
            self.reader=CrsReader(filename);self.index=0;self.advance()
        elif Path(filename).suffix.lower()=='.gif':
            self.movie=QMovie(str(filename));self.movie.frameChanged.connect(self.gif_frame)
            if not self.movie.isValid():raise ValueError('This GIF cannot be decoded.')
            self.movie.start()
        else:
            self.image=QImage(str(filename))
            if self.image.isNull():raise ValueError('Cannot decode this image.')
            self.draw_frame()
    def load_stream(self,paths):
        self.stop()
        try:self.reader=CrsReader(paths['temporary'],True,partial=True)
        except FileNotFoundError:self.reader=CrsReader(paths['complete'],True)
        self.index=0;self.advance()
    def finish_stream(self,filename):
        if self.reader is not None and getattr(self.reader,'partial',False):
            complete=CrsReader(filename,True);self.reader.close();self.reader=complete
        else:self.load(filename)
    def advance(self):
        try:
            self.image=self.reader.frame(self.index);delay=self.reader.delays[self.index]
            if self.playback_rate in(30,60):
                delay=1000//self.playback_rate;self.frame_fraction+=1000%self.playback_rate
                if self.frame_fraction>=self.playback_rate:self.frame_fraction-=self.playback_rate;delay+=1
            self.index=(self.index+1)%self.reader.frames;self.draw_frame();self.timer.start(max(10,delay))
        except PreviewFramePending:self.timer.start(20)
        except (OSError,ValueError):self.stop();self.setText('Preview file is unavailable or changed.')
    def gif_frame(self,*unused):
        if self.movie:self.image=self.movie.currentImage();self.draw_frame()
    def draw_frame(self):
        if self.image is not None:self.setPixmap(QPixmap.fromImage(self.image).scaled(self.size(),Qt.KeepAspectRatio,Qt.FastTransformation))
    def resizeEvent(self,event):
        super().resizeEvent(event);self.draw_frame()

class LibraryWorker(QThread):
    progress=pyqtSignal(int)
    completed=pyqtSignal(object)
    preview_ready=pyqtSignal(object)
    def __init__(self,job,parent):super().__init__(parent);self.job=job
    def run(self):
        try:self.completed.emit(dict(value=self.job(self.progress.emit,self.isInterruptionRequested)))
        except Exception as error:self.completed.emit(dict(error=str(error)))

def is_my2k(keyboard):
    return [s.get('count')for s in getattr(keyboard,'amk_rgb_strip',{}).get('strips',[])]==[19,19,8,1,8,4,2]

class CropPreview(MoviePreview):
    """Source-pixel square crop shared with the converter; GIF playback stays live."""
    def __init__(self):
        super().__init__();self.cropping=False;self.square=None;self.drag=None
    def load(self,filename):self.square=None;super().load(filename)
    def set_mode(self,index):self.cropping=index==1;self.update()
    def draw_frame(self):self.update()
    def geometry_for_image(self):
        if self.image is None:return QRectF()
        w,h=self.image.width(),self.image.height();scale=min(self.width()/w,self.height()/h)
        return QRectF((self.width()-w*scale)/2,(self.height()-h*scale)/2,w*scale,h*scale)
    def crop(self):
        if not self.cropping or self.image is None:return None
        if self.square is None:
            w,h=self.image.width(),self.image.height();side=min(w,h);self.square=((w-side)/2,(h-side)/2,side)
        x,y,side=self.square;return(int(x),int(y),max(1,int(side)))
    def paintEvent(self,event):
        if self.image is None:return super().paintEvent(event)
        p=QPainter(self);p.setRenderHint(QPainter.SmoothPixmapTransform,True);p.fillRect(self.rect(),Qt.black);rect=self.geometry_for_image();p.drawImage(rect,self.image)
        if self.crop()is not None:
            x,y,side=self.square;scale=rect.width()/self.image.width();crop=QRectF(rect.x()+x*scale,rect.y()+y*scale,side*scale,side*scale)
            p.setPen(QPen(Qt.white,2));p.drawRect(crop);p.fillRect(QRectF(crop.right()-7,crop.bottom()-7,14,14),QColor('#46b8ff'))
        p.end()
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton or self.crop()is None:return
        rect=self.geometry_for_image();scale=rect.width()/self.image.width();pos=((event.x()-rect.x())/scale,(event.y()-rect.y())/scale);x,y,side=self.square
        if abs(pos[0]-(x+side))*scale<16 and abs(pos[1]-(y+side))*scale<16:self.drag=('resize',pos,self.square)
        elif x<=pos[0]<=x+side and y<=pos[1]<=y+side:self.drag=('move',pos,self.square)
    def mouseMoveEvent(self,event):
        if not self.drag:return
        rect=self.geometry_for_image();scale=rect.width()/self.image.width();px,py=(event.x()-rect.x())/scale,(event.y()-rect.y())/scale
        kind,(ox,oy),(x,y,side)=self.drag;w,h=self.image.width(),self.image.height()
        if kind=='move':x=max(0,min(w-side,x+px-ox));y=max(0,min(h-side,y+py-oy))
        else:side=max(1,min(w-x,h-y,side+max(px-ox,py-oy)))
        self.square=(x,y,side);self.update()
    def mouseReleaseEvent(self,event):self.drag=None

class AnimationLibrary(QWidget):
    def __init__(self,formats):
        super().__init__();self.formats=formats;self.keyboard=None;self.worker=None;self.source=None;self.source_name=None;self.items={};self.mount=None;self.active=0
        self.cache=tempfile.TemporaryDirectory(prefix='vial-my2k-preview-');self.paused_timers=[];self.preview_cache={};self.preview_generation=0;self.preview_streaming=False
        outer=QVBoxLayout(self)
        self.maintenance_btn=QPushButton('Mount drive for maintenance…');self.maintenance_btn.clicked.connect(self.maintenance);outer.addWidget(self.maintenance_btn)
        self.general_active=False
        self.general_tools=QGroupBox('Display and animation tools',self)
        tools=QVBoxLayout(self.general_tools)
        test=QHBoxLayout();tools.addLayout(test);self.test_active=False
        self.test_start=QPushButton('Display Test');self.test_start.clicked.connect(lambda:self.display_test(1));self.test_start.setEnabled(False);test.addWidget(self.test_start)
        self.test_stop=QPushButton('Return to Animation');self.test_stop.clicked.connect(lambda:self.display_test(0));self.test_stop.setEnabled(False);test.addWidget(self.test_stop)
        self.test_fps=QLabel('Test FPS: —');test.addWidget(self.test_fps);test.addStretch()
        self.test_fps.setToolTip('Actual completed SPI frame transfers, not optical LCD scanout. The test is temporary and does not upload files or change your selected slot.')
        self.legacy_btn=QPushButton('Convert legacy animation to slot 1');self.legacy_btn.clicked.connect(self.import_legacy);tools.addWidget(self.legacy_btn)
        self.general_tools.hide()
        self.test_timer=QTimer(self);self.test_timer.setInterval(1000);self.test_timer.timeout.connect(self.poll_display_test)
        self.load_timer=QTimer(self);self.load_timer.setSingleShot(True);self.load_timer.timeout.connect(self.auto_refresh)
        self.page_active=False
        columns=QHBoxLayout();outer.addLayout(columns,1)
        left=QGroupBox('GIF converter');right=QGroupBox('Files on keyboard');columns.addWidget(left,1);columns.addWidget(right,1)
        l=QVBoxLayout(left);r=QVBoxLayout(right)
        self.source_preview=CropPreview();self.device_preview=MoviePreview();l.addWidget(self.source_preview,1);r.addWidget(self.device_preview,1)
        self.source_label=QLabel('Select an original GIF or image to preview at source resolution.');self.source_label.setWordWrap(True);l.addWidget(self.source_label)
        self.select_btn=QPushButton('Select file…');self.select_btn.clicked.connect(self.choose_source);l.addWidget(self.select_btn)
        self.fit=QComboBox();self.fit.addItems(['Native size — fit with padding','Crop to fit — drag square / resize blue corner']);self.fit.currentIndexChanged.connect(self.source_preview.set_mode);self.fit.setCurrentIndex(1);l.addWidget(self.fit)
        self.format=ClickComboBox()
        for f in formats:self.format.addItem(f['name'])
        self.format.setToolTip('MY-2K: 128 × 128 RGB565 CRS, up to 512 frames.');l.addWidget(self.format)
        self.convert_btn=QPushButton('Convert and save to desktop');self.convert_btn.clicked.connect(self.convert);l.addWidget(self.convert_btn)
        self.files=QListWidget();self.files.setMaximumHeight(200);r.addWidget(self.files)
        self.files.itemClicked.connect(lambda unused:self.preview())
        self.transfer_box=QGroupBox('Transfer GIF to keyboard')
        self.transfer_box.setStyleSheet('QGroupBox { background: palette(alternate-base); border: 1px solid palette(mid); border-radius: 5px; margin-top: 10px; padding: 12px 8px 8px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: bold; }')
        row=QHBoxLayout(self.transfer_box)
        self.slot=QComboBox()
        self.slot.setProperty('astroPopupRows',6)
        self.slot.setMaxVisibleItems(6)
        self.slot.setStyleSheet('QComboBox { combobox-popup: 0; }')
        self.slot.view().setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        for n in range(1,11):self.slot.addItem('Slot %02d'%n,n)
        row.addWidget(self.slot,1)
        self.upload_btn=QPushButton('Save preview to slot');self.upload_btn.clicked.connect(self.upload);row.addWidget(self.upload_btn)
        r.addWidget(self.transfer_box)
        self.delete_btn=QPushButton('Clear slot');self.delete_btn.clicked.connect(self.delete);r.addWidget(self.delete_btn)
        self.play_btn=QPushButton('Play selected slot on keyboard');self.play_btn.clicked.connect(self.play);r.addWidget(self.play_btn)
        self.status=QLabel('MY-2K: 128 × 128. Click an occupied slot to preview. Files are managed without mounting.');self.status.setWordWrap(True);outer.addWidget(self.status)
        self.populate()
    def populate(self):
        previous=self.selected_slot();self.files.clear()
        for n in range(1,11):
            info=self.items.get(n);text=slot_name(n)+' — '+('%.1f KiB'%(info['size']/1024)if info else'empty')
            item=QListWidgetItem(text);item.setData(Qt.UserRole,n);self.files.addItem(item)
        self.files.setCurrentRow((previous or 1)-1)
    def selected_slot(self):
        item=self.files.currentItem();return item.data(Qt.UserRole)if item else 0
    def invalidate_preview_cache(self):
        self.preview_cache.clear();self.preview_generation+=1
    def rebuild(self,keyboard):
        self.invalidate_preview_cache()
        self.keyboard=keyboard;self.items={};self.mount=None;self.populate();self.device_preview.stop()
        self.load_timer.stop()
        self.device_preview.playback_rate=None
        self.test_timer.stop();self.test_active=False;self.test_start.setEnabled(False);self.test_stop.setEnabled(False);self.test_fps.setText('Test FPS: —')
        self.status.setText('The animation list loads automatically when you open this tab.' if keyboard else 'Connect a supported MY-2K keyboard.')
        self.legacy_btn.setEnabled(keyboard is not None)
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Close and self.worker and self.worker.isRunning():
            self.worker.requestInterruption();event.ignore();return True
        return super().eventFilter(watched,event)
    def run_job(self,title,job,done,quiet=False,on_preview=None):
        if self.worker and self.worker.isRunning():return
        self.test_timer.stop();self.quiet=quiet
        self.window_owner=self.window();self.window_owner.installEventFilter(self)
        self.paused_timers=[]
        auxiliary=getattr(self.window_owner,'aux_display',None)
        if auxiliary:
            for name in ('ready_timer','save_timer','auto_clock_timer'):
                timer=getattr(auxiliary,name,None)
                if timer and timer.isActive():self.paused_timers.append((timer,timer.interval(),max(0,timer.remainingTime()),timer.isSingleShot()));timer.stop()
        general=getattr(self.window_owner,'misc',None)
        owners=((general,('performance_timer','wifi_timer')), (getattr(general,'sleep_mode',None),('apply_timer','poll_timer')))
        for owner,names in owners:
            for name in names:
                timer=getattr(owner,name,None)
                if timer and timer.isActive():self.paused_timers.append((timer,timer.interval(),max(0,timer.remainingTime()),timer.isSingleShot()));timer.stop()
        self.locked=hasattr(self.window_owner,'lock_ui')
        if self.locked:self.window_owner.lock_ui()
        self.progress=QProgressDialog(title,'Cancel',0,100,self.window_owner);self.progress.setWindowModality(Qt.WindowModal);self.progress.setMinimumDuration(1000 if quiet else 0);self.progress.setAutoClose(False)
        if not quiet:self.progress.show()
        self.worker=LibraryWorker(job,self)
        if on_preview:self.worker.preview_ready.connect(on_preview)
        self.worker.progress.connect(self.progress.setValue);self.progress.canceled.connect(self.worker.requestInterruption)
        self.worker.completed.connect(lambda result:self.complete(result,done));self.worker.finished.connect(self.worker.deleteLater);self.worker.start()
    def complete(self,result,done):
        self.progress.close();self.progress.deleteLater();self.window_owner.removeEventFilter(self)
        if self.locked:self.window_owner.unlock_ui()
        for timer,interval,remaining,single in self.paused_timers:timer.start(remaining if single else interval)
        self.paused_timers=[];self.worker=None
        if 'error'in result:
            if self.preview_streaming:self.device_preview.stop();self.preview_streaming=False
            self.status.setText(result['error'])
            if not self.quiet:QMessageBox.warning(self,'Animation operation failed',result['error'])
            return
        else:
            try:done(result['value'])
            except (OSError,RuntimeError,ValueError)as error:
                if self.preview_streaming:self.device_preview.stop();self.preview_streaming=False
                self.status.setText(str(error));QMessageBox.warning(self,'Animation operation failed',str(error))
        if self.test_active and self.general_active:self.test_timer.start()
    def activate(self):
        self.page_active=True
        if self.keyboard:self.load_timer.start(0)
    def deactivate(self):
        self.page_active=False;self.load_timer.stop()
    def auto_refresh(self):
        if self.page_active and self.keyboard and not(self.worker and self.worker.isRunning()):self.refresh(quiet=True)
    def activate_general_tools(self):
        self.general_active=True
        if self.keyboard and not(self.worker and self.worker.isRunning()):
            keyboard=self.keyboard
            def job(progress,cancel):
                client=AnimationClient(keyboard);caps=client.capabilities()
                return client.display_test() if caps['test_supported'] else None
            def done(result):
                if result is None:
                    self.test_start.setEnabled(False);self.test_stop.setEnabled(False);self.test_fps.setText('Display Test unavailable')
                else:self.show_test_status(result)
            self.run_job('Reading display test status…',job,done,quiet=True)
    def deactivate_general_tools(self):
        self.general_active=False;self.test_timer.stop()
    def choose_source(self):
        name,_=QFileDialog.getOpenFileName(self,'Select original GIF or image','','Original GIFs and images (*.gif *.png *.jpg *.jpeg *.bmp);;Converted keyboard animations (*.CRS *.crs *.anm *.sml *.bkg *.sts)')
        if name:
            try:
                source=Path(name)
                if source.stat().st_size>128*1024*1024:raise ValueError('Source exceeds the 128 MiB conversion limit.')
                cached=Path(self.cache.name)/('source-preview'+source.suffix)
                shutil.copyfile(source,cached)
                self.source_preview.load(cached);self.source=cached;self.source_name=source
                image=self.source_preview.image
                dimensions=(' — %d × %d source pixels'%(image.width(),image.height()))if image is not None else ''
                converted=source.suffix.lower()in('.crs','.anm','.sml','.bkg','.sts','.aux')
                self.source_label.setText(source.name+dimensions+(' (already converted)'if converted else ' (original)'))
                self.source_preview.setToolTip('Original source pixels and aspect ratio. Crop/conversion is applied only when saving or uploading.'if not converted else 'This source file is already converted; detail removed during its earlier conversion cannot be recovered.')
            except (OSError,ValueError)as error:QMessageBox.warning(self,'Cannot preview',str(error))

    def convert(self):
        if not self.source:self.status.setText('Select a GIF or image first.');return
        f=self.formats[self.format.currentIndex()];original=self.source_name or self.source
        default=Path.home()/'Desktop'/(original.stem+f['suffix']);name,_=QFileDialog.getSaveFileName(self,'Convert and save to desktop',str(default),f['filter'])
        if not name:return
        if not Path(name).suffix:name+=f['suffix']
        from vi_al_addons.my2k.animation import ANIM_MODES
        mode=ANIM_MODES[f['mode']];source=self.source;crop=self.source_preview.crop()
        self.run_job('Converting locally…',lambda p,c:convert_animation(source,name,mode['width'],mode['height'],mode['magic'].encode(),p,c,crop=crop),lambda result:self.status.setText('Saved %d frames to %s.'%(result['frames'],name)))
    def refresh(self,quiet=False):
        if not self.keyboard:return
        self.invalidate_preview_cache()
        keyboard=self.keyboard
        def job(progress,cancel):
            client=AnimationFilesClient(keyboard);client.capabilities();items={}
            for n in range(11):
                if cancel():raise RuntimeError('List loading cancelled.')
                info=client.info(n)
                if info:items[n]=info
            return items
        def done(items):
            self.items=items;self.populate()
            self.device_preview.playback_rate=None
            self.status.setText('Library loaded from keyboard; click a slot to preview. Animations use original GIF timing.')
        self.run_job('Reading library…',job,done,quiet=quiet)
    def show_test_status(self,result):
        self.test_active=result['active']
        self.test_fps.setText('Test FPS: %.1f%s'%(result['FPS'],' — transfer error'if result['error']else''))
        self.test_start.setEnabled(not result['active']);self.test_stop.setEnabled(result['active'])
        if not result['active']:self.status.setText('Selected animation restored; test mode was not saved.')
    def display_test(self,action):
        if not self.keyboard:return
        keyboard=self.keyboard
        self.run_job('Starting display test…'if action else'Restoring animation…',lambda p,c:AnimationClient(keyboard).display_test(action),self.show_test_status)
    def poll_display_test(self):
        if not self.keyboard or not self.general_active or not self.test_active or(self.worker and self.worker.isRunning()):return
        keyboard=self.keyboard
        self.run_job('Reading completed-frame FPS…',lambda p,c:AnimationClient(keyboard).display_test(),self.show_test_status,quiet=True)
    def preview(self):
        if self.worker and self.worker.isRunning():return
        info=self.items.get(self.selected_slot())
        if not info:self.device_preview.stop();self.status.setText('This slot is empty.');return
        cached=Path(self.cache.name)/('slot-%02d.CRS'%info['slot']);self.device_preview.stop();keyboard=self.keyboard
        key=(info['slot'],info['size'],self.preview_generation)
        if self.preview_cache.get(info['slot'])==key and cached.is_file():
            try:
                self.device_preview.load(cached);self.status.setText('Playing cached preview. Reopen Animations to reload the keyboard list and refresh previews.');return
            except (OSError,ValueError):self.preview_cache.pop(info['slot'],None)
        def loaded(unused):
            self.preview_cache[info['slot']]=key;self.device_preview.finish_stream(cached);self.preview_streaming=False
            self.status.setText('Fresh preview downloaded from keyboard; repeat clicks use this local copy.')
        self.preview_streaming=True
        def job(progress,cancel):
            return AnimationFilesClient(keyboard).download(info,cached,progress,cancel,preview_ready=lambda paths:self.worker.preview_ready.emit(paths))
        def streaming(paths):
            try:self.device_preview.load_stream(paths)
            except (OSError,ValueError):return
            self.status.setText('Playing fresh frames from keyboard; receiving the rest…')
            self.progress.setLabelText('Preview is playing; downloading remaining frames…')
            self.progress.adjustSize()
            bottom=self.window_owner.mapToGlobal(QPoint(20,max(20,self.window_owner.height()-self.progress.height()-30)));self.progress.move(bottom)
        self.run_job('Downloading fresh preview…',job,loaded,on_preview=streaming)
    def confirm_replace(self,slot):
        return slot not in self.items or QMessageBox.question(self,'Replace animation?',slot_name(slot)+' already exists. Replace this slot?',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Yes
    def upload(self):
        if not self.keyboard or not self.source:self.status.setText('Select a source and connect the keyboard first.');return
        slot=self.slot.currentData()
        if not self.confirm_replace(slot):return
        source=self.source;crop=self.source_preview.crop();keyboard=self.keyboard
        def job(progress,cancel):
            client=AnimationFilesClient(keyboard);client.capabilities()
            with tempfile.TemporaryDirectory(prefix='my2k-upload-')as folder:
                converted=Path(folder)/'converted.CRS';convert_animation(source,converted,progress=lambda n:progress(n//5),cancelled=cancel,crop=crop)
                return client.upload(converted,slot,replace=slot in self.items,progress=lambda n:progress(20+n*80//100),cancelled=cancel)
        self.run_job('Converting, uploading and checking transfer…',job,lambda filename:self.saved(filename,slot))
    def saved(self,filename,slot):
        keyboard=self.keyboard
        def done(unused):
            self.status.setText('Saved and verified '+filename);self.refresh()
        self.run_job('Confirming original animation timing…',lambda p,c:AnimationClient(keyboard).original_speed(),done)

    def upload_file(self):
        if not self.keyboard:return
        name,_=QFileDialog.getOpenFileName(self,'Upload converted animation','','MY-2K animations (*.CRS *.crs)')
        if not name:return
        slot=self.selected_slot()or self.slot.currentData()
        if not self.confirm_replace(slot):return
        keyboard=self.keyboard
        def job(progress,cancel):
            client=AnimationFilesClient(keyboard);client.capabilities();return client.upload(name,slot,slot in self.items,progress,cancel)
        self.run_job('Saving and verifying converted file…',job,lambda filename:self.saved(filename,slot))
    def delete(self):
        slot=self.selected_slot()
        if not slot:self.status.setText('Choose slot 1–10. Choose a numbered animation slot.');return
        if QMessageBox.question(self,'Clear slot?',slot_name(slot)+' will be removed.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return
        keyboard=self.keyboard;self.device_preview.stop()
        self.run_job('Clearing slot…',lambda p,c:AnimationFilesClient(keyboard).clear(slot),lambda unused:self.refresh())
    def import_legacy(self):
        if not self.keyboard:return
        keyboard=self.keyboard
        def inspect(progress,cancel):
            client=AnimationFilesClient(keyboard);client.capabilities()
            if not client.info(0):raise RuntimeError('There is no legacy animation to convert.')
            return client.info(1) is not None
        def confirm(replace):
            message='Move the current legacy animation into anamations/animation_01.CRS?'+(' The existing slot 1 will be replaced.'if replace else'')
            if QMessageBox.question(self,'Convert legacy animation to slot 1?',message,QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return
            def job(progress,cancel):
                AnimationFilesClient(keyboard).import_legacy(replace)
                selection=AnimationClient(keyboard);selection.original_speed();return selection.selection(1)
            self.run_job('Converting legacy animation…',job,lambda unused:self.refresh())
        self.run_job('Checking legacy animation and slot 1…',inspect,confirm)
    def download(self):
        info=self.items.get(self.selected_slot())
        if not info:return
        name,_=QFileDialog.getSaveFileName(self,'Save selected animation',str(Path.home()/'Desktop'/info['name']),'MY-2K animations (*.CRS)')
        if not name:return
        keyboard=self.keyboard
        self.run_job('Downloading animation…',lambda p,c:AnimationFilesClient(keyboard).download(info,name,p,c),lambda unused:self.status.setText('Saved '+name))
    def play(self):
        slot=self.selected_slot()
        if not slot:return
        keyboard=self.keyboard
        def job(progress,cancel):
            client=AnimationClient(keyboard);client.original_speed();return client.selection(slot)
        self.run_job('Selecting animation…',job,lambda result:self.status.setText('Playing slot %02d.'%result['active']))
    def maintenance(self):
        if not self.keyboard:return
        if QMessageBox.question(self,'Mount for maintenance?','This deliberately enters USB storage mode and mounts the MY-2K asset drive. Normal library actions do not need this. Eject the drive before using MY2K_STORAGE_TOGGLE to return.',QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:return
        keyboard=self.keyboard
        from vi_al_addons.my2k.animation_maintenance import mount_maintenance
        self.run_job('Entering maintenance and waiting for the drive…',lambda p,c:mount_maintenance(keyboard,c),lambda path:self.status.setText('Maintenance drive mounted at '+path+'. Eject it, then use MY2K_STORAGE_TOGGLE to return.'))
