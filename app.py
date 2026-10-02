"""Spanish desktop UI. All Tk operations stay on the main thread."""
import ctypes, hashlib, json, os, queue, shutil, subprocess, sys, tempfile, threading, zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core import scan, quarantine, restore, write_csv, Cancelled

APP_VERSION = '3.0.4'

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(f'DJ Duplicate Finder v{APP_VERSION.split(".")[0]}'); self.geometry('1180x760'); self.minsize(680, 480)
        bundle_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        icon_file = bundle_root / 'assets' / 'DJ_Duplicate_Finder.ico'
        if icon_file.is_file():
            try: self.iconbitmap(default=str(icon_file))
            except tk.TclError: pass
        png_icon_file = bundle_root / 'assets' / 'DJ_Duplicate_Finder.png'
        if png_icon_file.is_file():
            try:
                self._window_icon = tk.PhotoImage(file=str(png_icon_file))
                self.iconphoto(True, self._window_icon)
            except tk.TclError: pass
        self.messages = queue.Queue(); self.cancel = threading.Event(); self.report = None; self.selected = set(); self.rows = {}; self.busy = False
        self.folder = tk.StringVar(); self.audio = tk.BooleanVar(value=True); self.status = tk.StringVar(value='Selecciona una carpeta para comenzar.')
        self.settings_path = self.user_settings_path()
        self.appearance = tk.StringVar(value=self.load_appearance())
        self.style = ttk.Style(self); self.style.theme_use('clam')
        container = ttk.Frame(self, padding=18); container.pack(fill='both', expand=True)
        header = ttk.Frame(container); header.pack(fill='x')
        ttk.Label(header, text=f'DJ Duplicate Finder v{APP_VERSION.split(".")[0]}', style='Title.TLabel').pack(side='left', anchor='w')
        ttk.Label(header, text='Apariencia').pack(side='right', padx=(8, 4))
        self.theme_choice = ttk.Combobox(header, textvariable=self.appearance, values=('Clara', 'Oscura'), state='readonly', width=10)
        self.theme_choice.pack(side='right'); self.theme_choice.bind('<<ComboboxSelected>>', self.change_appearance)
        self.apply_theme()
        ttk.Label(container, text='Detector de duplicados Audio y Video').pack(anchor='w', pady=(4, 14))
        line = ttk.Frame(container); line.pack(fill='x')
        ttk.Entry(line, textvariable=self.folder).pack(side='left', fill='x', expand=True, ipady=5)
        self.pick = ttk.Button(line, text='Elegir carpeta', command=self.choose); self.pick.pack(side='left', padx=(8, 6))
        self.analyze = ttk.Button(line, text='Analizar', style='Accent.TButton', command=self.start); self.analyze.pack(side='left')
        self.check = ttk.Checkbutton(container, text='Analizar todo el audio con FFmpeg (más lento). Desmarcar para detectar solo copias exactas.', variable=self.audio); self.check.pack(anchor='w', pady=10)
        self.progress = ttk.Progressbar(container, mode='indeterminate'); self.progress.pack(fill='x')
        self.status_label = ttk.Label(container, textvariable=self.status, wraplength=1080); self.status_label.pack(anchor='w', pady=8)
        self.bind('<Configure>', self.resize_labels, add='+')
        actions = ttk.Frame(container); actions.pack(fill='x', pady=(0, 6))
        self.action_buttons = []
        commands = [('Marcar copias exactas',self.mark_exact),('Reproducir',self.play),('Exportar CSV',self.export),('Ver incidencias',self.errors),('Mover marcados',self.move),('Restaurar sesión',self.restore_session)]
        if sys.platform == 'win32': commands.append(('Aplicar actualización',self.apply_update))
        for title, command in commands:
            b = ttk.Button(actions,text=title,command=command); self.action_buttons.append(b)
        self.cancel_button = ttk.Button(actions,text='Cancelar análisis',command=self.cancel.set)
        self.action_buttons.append(self.cancel_button)
        actions.bind('<Configure>', lambda event: self.layout_actions(event.width), add='+')
        columns = ('select', 'kind', 'file', 'duration', 'bitrate', 'keep')
        frame = ttk.Frame(container); frame.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(frame, columns=columns, show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='Grupo / archivo'); self.tree.column('#0', width=180)
        for key, title, width in [('select','Mover',55),('kind','Coincidencia',205),('file','Ruta',370),('duration','Segundos',75),('bitrate','kbps',65),('keep','Sugerencia',105)]:
            self.tree.heading(key,text=title); self.tree.column(key,width=width,stretch=key in ('file','kind'))
        y = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview); x = ttk.Scrollbar(frame, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set); self.tree.grid(row=0,column=0,sticky='nsew'); y.grid(row=0,column=1,sticky='ns'); x.grid(row=1,column=0,sticky='ew'); frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        self.tree.bind('<Double-1>', self.toggle); self.tree.bind('<space>', self.toggle)
        self.hint_labels = [
            ttk.Label(container, text='Doble clic o barra espaciadora en un archivo para marcarlo. La similitud es una medida técnica, no una garantía de identidad.', wraplength=1080),
            ttk.Label(container, text='La cuarentena conserva los archivos. Mover música puede dejar rutas pendientes en Serato/Rekordbox; revisa tus playlists y cues antes de confirmar.', wraplength=1080),
        ]
        self.hint_labels[0].pack(anchor='w', pady=8)
        self.hint_labels[1].pack(anchor='w')
        self.after_idle(lambda: self.layout_actions(actions.winfo_width()))
        self.protocol('WM_DELETE_WINDOW',self.close); self.after(100,self.poll); self.after(800,self.refresh_windows_shortcuts)

    def choose(self):
        folder = filedialog.askdirectory()
        if folder: self.folder.set(folder)
    def set_busy(self,value):
        self.busy=value
        for b in [self.pick,self.analyze,self.check,*self.action_buttons,self.cancel_button]: b.configure(state='disabled' if value else 'normal')
        self.cancel_button.configure(state='normal' if value else 'disabled')
        if value: self.progress.start()
        else: self.progress.stop()
    def work(self,fn,kind):
        self.set_busy(True)
        def worker():
            try: self.messages.put((kind,fn()))
            except Cancelled: self.messages.put(('cancelled',None))
            except Exception as exc: self.messages.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()
    def start(self):
        if self.busy: return
        root = self.folder.get(); acoustic=self.audio.get()
        if not Path(root).is_dir(): messagebox.showerror('Carpeta','Selecciona una carpeta existente'); return
        self.report=None; self.selected.clear(); self.rows.clear(); self.tree.delete(*self.tree.get_children()); self.cancel.clear()
        self.work(lambda:scan(root,acoustic,lambda s:self.messages.put(('progress',s)),self.cancel),'report')
    def poll(self):
        try:
            while True:
                kind,value=self.messages.get_nowait()
                if kind=='progress': self.status.set(value); continue
                self.set_busy(False)
                if kind=='report': self.report=value; self.render(); self.status.set(f'{len(value.files)} archivos · {len(value.matches)} coincidencias · {len(value.errors)} incidencias')
                elif kind=='moved':
                    self.report=None; self.selected.clear(); self.rows.clear(); self.tree.delete(*self.tree.get_children())
                    self.status.set('Movimiento completado. Vuelve a analizar para actualizar los resultados.')
                    messagebox.showinfo('Cuarentena',f'Archivos conservados en cuarentena. Registro para restaurar:\n{value}')
                elif kind=='restored':
                    self.report=None; self.rows.clear(); self.selected.clear(); self.tree.delete(*self.tree.get_children()); self.status.set(f'{value} archivos restaurados. Vuelve a analizar.')
                elif kind=='cancelled': self.status.set('Análisis cancelado. No se movió ningún archivo.')
                else:
                    self.status.set('Operación interrumpida; revisa el detalle.'); messagebox.showerror('Detalle',value)
                    if self.report: self.report=None; self.selected.clear(); self.rows.clear(); self.tree.delete(*self.tree.get_children())
        except queue.Empty: pass
        self.after(100,self.poll)
    def render(self):
        self.tree.delete(*self.tree.get_children()); self.rows.clear()
        for i,m in enumerate(self.report.matches):
            parent=self.tree.insert('','end',text=f'Coincidencia {i+1}',values=('',m.kind,'','','',f'{m.score*100:.1f}%'),open=True)
            for f in (m.a,m.b):
                row=self.tree.insert(parent,'end',text=f.path.name,values=('☑' if f.path in self.selected else '☐','',str(f.path),f'{f.duration:.1f}' if f.duration else '—',round(f.bitrate/1000) if f.bitrate else '—','Conservar*' if f.path==m.keep else 'Revisar'))
                self.rows[row]=f.path
    def toggle(self,event=None):
        if self.busy or not self.tree.selection(): return
        p=self.rows.get(self.tree.selection()[0])
        if p is None: return
        if p in self.selected: self.selected.remove(p)
        else: self.selected.add(p)
        for row,path in self.rows.items(): self.tree.set(row,'select','☑' if path in self.selected else '☐')
        self.status.set(f'{len(self.selected)} archivos marcados para cuarentena')
    def mark_exact(self):
        if not self.report: return
        self.selected={m.b.path if m.keep==m.a.path else m.a.path for m in self.report.matches if m.kind=='Copia exacta'}; self.render()
        self.status.set(f'{len(self.selected)} copias exactas marcadas. Revisa la selección.')
    def play(self):
        if not self.tree.selection(): return
        p=self.rows.get(self.tree.selection()[0])
        if not p: return
        try:
            if sys.platform=='win32': os.startfile(p)
            else: subprocess.Popen(['open' if sys.platform=='darwin' else 'xdg-open',str(p)])
        except Exception as exc: messagebox.showerror('Reproducir',str(exc))
    def export(self):
        if not self.report: return
        p=filedialog.asksaveasfilename(defaultextension='.csv',initialfile='Duplicados_DJ.csv',filetypes=[('CSV','*.csv')])
        if p:
            try: write_csv(self.report,p); self.status.set('Reporte CSV exportado.')
            except Exception as exc: messagebox.showerror('Exportar',str(exc))
    def errors(self):
        if not self.report: return
        window=tk.Toplevel(self); window.title('Incidencias del análisis'); window.geometry('820x400')
        window.configure(bg=self.colors['window'])
        text=tk.Text(window,wrap='word',bg=self.colors['tree'],fg=self.colors['text'],insertbackground=self.colors['insert'],selectbackground=self.colors['selected']); text.pack(fill='both',expand=True); text.insert('1.0','\n\n'.join(self.report.errors) or 'Sin incidencias.'); text.configure(state='disabled')
    def move(self):
        if not self.report or not self.selected: return
        total=sum(f.size for f in self.report.files if f.path in self.selected)
        detail='\n'.join(str(p) for p in sorted(self.selected))
        window=tk.Toplevel(self); window.title('Revisar movimiento'); window.geometry('850x450'); window.transient(self); window.grab_set()
        window.configure(bg=self.colors['window'])
        ttk.Label(window,text=f'{len(self.selected)} archivos · {total/1024**2:.1f} MB se moverán a _DJ_DUPLICADOS.\nRevisa audio, versiones, playlists y cues antes de confirmar.',padding=12).pack(anchor='w')
        text=tk.Text(window,wrap='word',bg=self.colors['tree'],fg=self.colors['text'],insertbackground=self.colors['insert'],selectbackground=self.colors['selected']); text.pack(fill='both',expand=True,padx=12); text.insert('1.0',detail); text.configure(state='disabled')
        def confirm():
            window.destroy(); report=self.report; selected=set(self.selected); self.work(lambda:quarantine(report,selected),'moved')
        ttk.Button(window,text='Confirmar y mover a cuarentena',command=confirm).pack(pady=10)
        ttk.Button(window,text='Volver',command=window.destroy).pack(pady=(0,10))
    def restore_session(self):
        p=filedialog.askopenfilename(title='Selecciona restaurar.json dentro de _DJ_DUPLICADOS',filetypes=[('Registro JSON','*.json')])
        if p and messagebox.askyesno('Restaurar','¿Restaurar esta sesión a sus rutas originales? No se sobrescribirán archivos existentes.'):
            self.work(lambda:restore(p),'restored')
    def close(self):
        if self.busy:
            messagebox.showinfo('Operación en curso','Cancela el análisis o espera a que termine la operación antes de cerrar.'); return
        self.destroy()

    def refresh_windows_shortcuts(self):
        if sys.platform != 'win32':
            return
        bundle_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        script = bundle_root / 'assets' / 'refresh_taskbar_icon.ps1'
        icon_file = bundle_root / 'assets' / 'DJ_Duplicate_Finder.ico'
        if not script.is_file() or not icon_file.is_file():
            return
        try:
            subprocess.Popen(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', str(script), str(Path(sys.executable).resolve()), str(icon_file)],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), close_fds=True,
            )
        except OSError:
            pass

    @staticmethod
    def user_settings_path():
        appdata = os.environ.get('APPDATA')
        if appdata:
            base = Path(appdata)
        elif sys.platform == 'darwin':
            base = Path.home() / 'Library' / 'Application Support'
        else:
            base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
        return base / 'DJ Duplicate Finder' / 'settings.json'

    def load_appearance(self):
        try:
            value = json.loads(self.settings_path.read_text(encoding='utf-8')).get('appearance', 'Clara')
            return value if value in ('Clara', 'Oscura') else 'Clara'
        except (OSError, ValueError, AttributeError):
            return 'Clara'

    def change_appearance(self, _event=None):
        self.apply_theme()
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps({'appearance': self.appearance.get()}, ensure_ascii=False, indent=2), encoding='utf-8')
        except OSError as exc:
            messagebox.showwarning('Apariencia', f'El tema se aplicó, pero no se pudo guardar para la próxima vez:\n{exc}')

    def apply_theme(self):
        dark = self.appearance.get() == 'Oscura'
        colors = ({
            'window': '#1B2221', 'panel': '#232C2A', 'text': '#E7EFEC', 'muted': '#BBCBC5',
            'accent': '#8CCBBB', 'button': '#354440', 'button_text': '#ECF4F1', 'button_active': '#455A54',
            'disabled': '#53635E', 'tree': '#202725', 'heading': '#303C38', 'selected': '#385E53',
            'selected_text': '#F4FAF7', 'insert': '#FFFFFF',
        } if dark else {
            'window': '#F3F7F5', 'panel': '#F3F7F5', 'text': '#223A34', 'muted': '#344B45',
            'accent': '#245A52', 'button': '#E1ECE8', 'button_text': '#23453F', 'button_active': '#D0E2DC',
            'disabled': '#E9EFEC', 'tree': '#FFFFFF', 'heading': '#E1ECE8', 'selected': '#CDE4DC',
            'selected_text': '#173F38', 'insert': '#263A35',
        })
        self.colors = colors
        self.configure(bg=colors['window'])
        s = self.style
        ui_font = 'Helvetica Neue' if sys.platform == 'darwin' else 'Segoe UI'
        s.configure('.', font=(ui_font, 10), background=colors['panel'], foreground=colors['text'])
        s.configure('TFrame', background=colors['panel'])
        s.configure('TLabel', background=colors['panel'], foreground=colors['muted'])
        s.configure('Title.TLabel', font=(ui_font, 22, 'bold'), foreground=colors['accent'])
        s.configure('TButton', padding=(10, 7), background=colors['button'], foreground=colors['button_text'])
        s.map('TButton', background=[('active', colors['button_active']), ('disabled', colors['disabled'])], foreground=[('disabled', colors['muted'])])
        s.configure('Accent.TButton', padding=(12, 8), background='#356F68' if not dark else '#397B6E', foreground='white', font=(ui_font, 10, 'bold'))
        s.map('Accent.TButton', background=[('active', '#2B605A' if not dark else '#4A9384'), ('disabled', colors['disabled'])])
        s.configure('TCheckbutton', background=colors['panel'], foreground=colors['muted'])
        s.map('TCheckbutton', background=[('active', colors['panel'])], foreground=[('active', colors['text'])])
        s.configure('TCombobox', fieldbackground=colors['tree'], background=colors['button'], foreground=colors['text'], arrowcolor=colors['text'])
        s.map('TCombobox', fieldbackground=[('readonly', colors['tree'])], foreground=[('readonly', colors['text'])])
        s.configure('Treeview', rowheight=29, background=colors['tree'], fieldbackground=colors['tree'], foreground=colors['text'])
        s.map('Treeview', background=[('selected', colors['selected'])], foreground=[('selected', colors['selected_text'])])
        s.configure('Treeview.Heading', background=colors['heading'], foreground=colors['text'], font=(ui_font, 9, 'bold'), padding=6)
        s.map('Treeview.Heading', background=[('active', colors['button_active'])])

    def layout_actions(self, width):
        if width <= 1 or not hasattr(self, 'action_buttons'):
            return
        cols = 4 if width >= 1040 else 3 if width >= 800 else 2 if width >= 640 else 1
        if getattr(self, '_action_cols', None) == cols:
            return
        self._action_cols = cols
        for button in self.action_buttons:
            button.grid_forget()
        for col in range(4):
            self.action_buttons[0].master.columnconfigure(col, weight=1 if col < cols else 0, uniform='toolbar' if col < cols else '')
        for i, button in enumerate(self.action_buttons):
            button.grid(row=i // cols, column=i % cols, sticky='ew', padx=(0, 7), pady=(0, 6))

    def resize_labels(self, event):
        if event.widget is self:
            width=max(240, event.width-52)
            self.status_label.configure(wraplength=width)
            for label in self.hint_labels:
                label.configure(wraplength=width)

    def apply_update(self):
        if sys.platform != 'win32':
            messagebox.showinfo('Actualización', 'La actualización incremental está disponible en la versión de Windows.')
            return
        package=filedialog.askopenfilename(title='Selecciona el paquete de actualización',filetypes=[('Actualización DJ Duplicate Finder','*.zip')])
        if not package: return
        staging=None
        try:
            staging=Path(tempfile.mkdtemp(prefix='djdf-update-'))
            with zipfile.ZipFile(package,'r') as archive:
                names=archive.namelist()
                if len(names)>10000 or 'manifest.json' not in names: raise ValueError('El paquete no contiene un manifiesto válido.')
                manifest=json.loads(archive.read('manifest.json').decode('utf-8'))
                if manifest.get('product') != 'DJ Duplicate Finder': raise ValueError('El paquete no corresponde a esta aplicación.')
                version=str(manifest['version'])
                def version_tuple(value): return tuple(int(part) for part in value.split('.'))
                if version_tuple(version)<=version_tuple(APP_VERSION): raise ValueError('El paquete debe ser de una versión posterior a la instalada.')
                source_version=manifest.get('from_version')
                if source_version and version_tuple(source_version)!=version_tuple(APP_VERSION): raise ValueError(f'Este paquete es para la versión {source_version}, no para la {APP_VERSION}.')
                files=manifest.get('files')
                if not isinstance(files,list) or not files: raise ValueError('El manifiesto no enumera archivos para actualizar.')
                root=Path(sys.executable).resolve().parent
                payload=staging/'payload'; payload.mkdir()
                for item in files:
                    rel=Path(item['path'])
                    if rel.is_absolute() or not rel.parts or any(part in ('..','.') for part in rel.parts) or ':' in item['path']:
                        raise ValueError('El paquete contiene una ruta no permitida.')
                    entry='payload/'+rel.as_posix()
                    data=archive.read(entry)
                    if hashlib.sha256(data).hexdigest().lower()!=str(item['sha256']).lower(): raise ValueError('La verificación de integridad falló.')
                    target=payload.joinpath(*rel.parts); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
            if not (payload/'DJ Duplicate Finder.exe').is_file(): raise ValueError('El paquete no incluye el ejecutable actualizado.')
            script=staging/'apply-update.ps1'
            script.write_text("""param([int]$WaitForPid,[string]$InstallRoot,[string]$PayloadRoot,[string]$Executable,[string]$NewVersion)\n$ErrorActionPreference = 'Stop'\ntry {\n  $p = Get-Process -Id $WaitForPid -ErrorAction SilentlyContinue\n  if ($p) { $p.WaitForExit() }\n  Get-ChildItem -LiteralPath $PayloadRoot | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $InstallRoot -Recurse -Force }\n  Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DJDuplicateFinder' -Name DisplayVersion -Value $NewVersion -ErrorAction SilentlyContinue\n  Start-Process -FilePath $Executable -WorkingDirectory $InstallRoot\n} catch {\n  Add-Type -AssemblyName System.Windows.Forms\n  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Error al actualizar') | Out-Null\n}\n""",encoding='utf-8')
            root=str(Path(sys.executable).resolve().parent); exe=str(Path(sys.executable).resolve())
            args=['-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',str(script),str(os.getpid()),root,str(payload),exe,version]
            subprocess.Popen(['powershell.exe',*args],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
            self.status.set(f'Preparando actualización a v{version}… La aplicación se cerrará y volverá a abrirse.')
            self.after(600,self.destroy)
        except Exception as exc:
            if staging: shutil.rmtree(staging,ignore_errors=True)
            messagebox.showerror('Actualización',f'No se pudo aplicar el paquete:\n{exc}')

def configure_bundled_ffmpeg():
    """Prefer the FFmpeg tools shipped beside the frozen application."""
    bundle_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    ffmpeg_dir = bundle_root / 'ffmpeg'
    suffix = '.exe' if sys.platform == 'win32' else ''
    if (ffmpeg_dir / f'ffmpeg{suffix}').is_file() and (ffmpeg_dir / f'ffprobe{suffix}').is_file():
        os.environ['PATH'] = str(ffmpeg_dir) + os.pathsep + os.environ.get('PATH', '')

if __name__=='__main__':
    configure_bundled_ffmpeg()
    App().mainloop()
