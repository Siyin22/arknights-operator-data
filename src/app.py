"""Desktop entry point for non-programmers."""
import os
import queue
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
from tkinter import font as tkfont
from common import APP, ARCHIVE, VERSION, find_game, read_json, write_json
from pipeline import Pipeline,Cancelled,lock
from github_sync import upload,UploadError
from archive_store import REPOSITORY
from version_compare import tags,write_comparison,version_label,load_snapshot


class App:
    def __init__(self,root):
        self.root=root;self.worker=None;self.events=queue.Queue();self.cancel=threading.Event();self.failed=None
        root.title('明日方舟干员模组数据工具');root.geometry('940x860');root.minsize(900,830)
        root.configure(bg='#F3F6F8')
        families={name.casefold():name for name in tkfont.families(root)}
        font_family=next((families[name.casefold()] for name in ('LXGW WenKai','霞鹜文楷','Microsoft YaHei','微软雅黑') if name.casefold() in families),'微软雅黑')
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont','TkCaptionFont','TkSmallCaptionFont','TkIconFont','TkTooltipFont'):
            tkfont.nametofont(name,root=root).configure(family=font_family)
        style=ttk.Style();style.theme_use('clam')
        style.configure('.',font=(font_family,10),background='#F3F6F8',foreground='#203342')
        style.configure('TButton',padding=(14,8))
        style.configure('Accent.TButton',background='#156B78',foreground='white',font=(font_family,11,'bold'))
        style.map('Accent.TButton',background=[('active','#105461'),('disabled','#A5BAC0')])
        style.configure('Title.TLabel',font=(font_family,22,'bold'))
        style.configure('Hint.TLabel',foreground='#617784')
        frame=ttk.Frame(root,padding=28);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='明日方舟干员模组数据工具',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='按官方版本保存干员与模组，上传 GitHub；历史版本交给 Git 管理。',style='Hint.TLabel').pack(anchor='w',pady=(6,24))
        ttk.Label(frame,text='游戏安装目录').pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(6,8))
        found=find_game();self.path=tk.StringVar(value=str(found) if found else '')
        self.entry=ttk.Entry(row,textvariable=self.path);self.entry.pack(side='left',fill='x',expand=True,ipady=5)
        self.browse=ttk.Button(row,text='选择目录',command=self.choose);self.browse.pack(side='left',padx=(10,0))
        ttk.Label(frame,text='选择包含 Arknights.exe 的文件夹。开始前请等待游戏更新完成。',style='Hint.TLabel').pack(anchor='w')
        buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=(22,14))
        self.start_button=ttk.Button(buttons,text='提取并上传 GitHub',style='Accent.TButton',command=self.start);self.start_button.pack(side='left')
        self.stop_button=ttk.Button(buttons,text='停止提取',state='disabled',command=self.stop);self.stop_button.pack(side='left',padx=10)
        ttk.Button(buttons,text='打开 GitHub',command=lambda:webbrowser.open('https://github.com/'+REPOSITORY)).pack(side='right')
        self.retry_button=ttk.Button(buttons,text='重试上传',command=self.retry_upload);self.retry_button.pack(side='right',padx=10)
        report_row=ttk.Frame(frame);report_row.pack(fill='x',pady=(0,14))
        self.open_report_button=ttk.Button(report_row,text='查看报告 / 导出图片',style='Accent.TButton',command=lambda:self.open_result('更新报告.html'));self.open_report_button.pack(side='left')
        ttk.Label(report_row,text='新增 / 修改 / 移除 · 满级满信赖 · 技能与模组效果',style='Hint.TLabel').pack(side='left',padx=12)
        versions=ttk.Frame(frame);versions.pack(fill='x',pady=(0,16))
        ttk.Label(versions,text='对比数据版本').pack(side='left')
        self.before=ttk.Combobox(versions,state='readonly',width=12);self.before.pack(side='left',padx=10)
        ttk.Label(versions,text='→').pack(side='left')
        self.after=ttk.Combobox(versions,state='readonly',width=15);self.after.pack(side='left',padx=10)
        self.compare_button=ttk.Button(versions,text='查看版本差异',command=self.compare_versions);self.compare_button.pack(side='left')
        self.status=tk.StringVar(value='就绪 · 重复提取相同资源版本会自动跳过，不再复制整套文件。')
        ttk.Label(frame,textvariable=self.status,wraplength=800).pack(anchor='w',pady=(0,8))
        self.bar=ttk.Progressbar(frame,mode='indeterminate');self.bar.pack(fill='x')
        self.summary=tk.StringVar()
        ttk.Label(frame,textvariable=self.summary,wraplength=800,style='Hint.TLabel').pack(anchor='w',pady=(12,18))
        ttk.Label(frame,text='运行记录').pack(anchor='w')
        logframe=ttk.Frame(frame);logframe.pack(fill='both',expand=True,pady=(6,12))
        self.log=tk.Text(logframe,height=7,wrap='word',state='disabled',font=(font_family,10),relief='flat',bg='white',fg='#203342',padx=12,pady=10)
        self.log.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(logframe,command=self.log.yview);scrollbar.pack(side='right',fill='y');self.log.configure(yscrollcommand=scrollbar.set)
        footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',before=logframe)
        ttk.Button(footer,text='使用说明',command=lambda:os.startfile(APP/'使用说明.txt')).pack(side='left')
        self.diagnostic_button=ttk.Button(footer,text='打开本次诊断目录',state='disabled',command=self.open_diagnostic);self.diagnostic_button.pack(side='left',padx=10)
        ttk.Label(footer,text=f'国服 PC · v{VERSION}',style='Hint.TLabel').pack(side='right')
        self.refresh();self.append('本地仅保留一套版本数据。上传失败可直接重试，不用重新提取。')
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(150,self.poll)

    def append(self,line):
        self.log.configure(state='normal');self.log.insert('end',line.strip()+'\n');self.log.see('end');self.log.configure(state='disabled')

    def refresh(self):
        present=(ARCHIVE/'version.json').is_file()
        self.open_report_button.configure(state='normal' if (ARCHIVE/'更新报告.html').is_file() else 'disabled')
        busy=self.worker and self.worker.is_alive()
        self.retry_button.configure(state='normal' if present and not busy else 'disabled')
        try:
            versions=tags(ARCHIVE) if present else []
            self.before.configure(values=versions);self.after.configure(values=versions)
            if versions:
                self.before.set(versions[-2] if len(versions)>1 else versions[0]);self.after.set(versions[-1])
                info=read_json(ARCHIVE/'version.json')
                self.summary.set(f"{version_label(info)} · 已保存 {len(versions)} 个数据版本\nGitHub：{REPOSITORY}"
                    + ('\n目前只有一个版本；下次更新后可选择两个版本比较。' if len(versions)==1 else ''))
            else:self.summary.set('尚无版本数据。首次提取将建立基准并上传 GitHub。')
            self.compare_button.configure(state='normal' if len(versions)>1 and not busy else 'disabled')
        except (ValueError,KeyError,OSError) as exc:self.summary.set('版本读取失败：'+str(exc))

    def choose(self):
        path=filedialog.askdirectory(title='选择包含 Arknights.exe 的目录',initialdir=self.path.get() or str(APP))
        if path:self.path.set(path)

    def start(self):
        if self.worker and self.worker.is_alive():return
        path=self.path.get().strip()
        if not path:
            messagebox.showinfo('请选择游戏目录','请选择包含 Arknights.exe 的游戏安装目录。');return
        write_json(APP/'settings.json',{'game':path})
        self.cancel=threading.Event();self.failed=None;self.diagnostic_button.configure(state='disabled')
        self.start_button.configure(state='disabled');self.stop_button.configure(state='normal')
        self.retry_button.configure(state='disabled');self.compare_button.configure(state='disabled')
        self.entry.configure(state='disabled');self.browse.configure(state='disabled')
        self.status.set('正在准备提取…');self.bar.start(15);self.append('开始提取当前数据。')
        def work():
            pipeline=Pipeline(path,emit=lambda s:self.events.put(('log',s)),cancel=self.cancel)
            try:
                result=pipeline.run()
                if self.cancel.is_set():raise Cancelled('已停止；本地已保存的版本可稍后上传。')
                self.events.put(('log','正在上传 GitHub…'))
                with lock():url=upload(result)
                self.events.put(('success',url))
            except UploadError as exc:self.events.put(('upload_failure',str(exc)))
            except Exception as exc:self.events.put(('failure',(str(exc),str(pipeline.run_dir) if pipeline.run_dir else None,isinstance(exc,Cancelled))))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def stop(self):
        self.cancel.set();self.stop_button.configure(state='disabled');self.status.set('正在停止，请稍候…')

    def poll(self):
        try:
            while True:
                event,value=self.events.get_nowait()
                if event=='log':
                    value=value.strip()
                    if re.match(r'[1-7]/7 ',value):self.status.set(value)
                    if value=='正在上传 GitHub…':self.status.set(value);self.stop_button.configure(state='disabled')
                    if re.search(r'[\u4e00-\u9fff]',value):self.append(value)
                else:
                    self.bar.stop();self.start_button.configure(state='normal');self.stop_button.configure(state='disabled')
                    self.entry.configure(state='normal');self.browse.configure(state='normal');self.worker=None;self.refresh()
                    if event=='success':
                        self.status.set('已上传 GitHub · 可查看报告、分别导出资料图片，或选择两个数据版本对比。');self.append('仓库：'+value)
                    elif event=='upload_failure':
                        self.status.set('本地版本已保存，上传未完成 · 点击“重试上传”。');self.append(value)
                    else:
                        error,folder,cancelled=value;self.failed=folder
                        self.status.set('已停止 · 上次成功的结果仍可使用。' if cancelled else '提取未完成 · 请查看诊断目录，上次成功的结果仍可使用。')
                        self.append(error)
                        if folder:self.diagnostic_button.configure(state='normal');self.append('诊断目录：'+folder)
                        if not cancelled:messagebox.showerror('提取未完成',error[:450]+'\n\n请把诊断目录中的“诊断包.zip”交给 AI 排查。')
        except queue.Empty:pass
        self.root.after(150,self.poll)

    def open_result(self,sub=''):
        if (ARCHIVE/'version.json').exists():os.startfile(ARCHIVE/sub if sub else ARCHIVE)

    def retry_upload(self):
        if self.worker and self.worker.is_alive():return
        self.start_button.configure(state='disabled');self.retry_button.configure(state='disabled');self.compare_button.configure(state='disabled')
        self.status.set('正在上传 GitHub…');self.bar.start(15)
        def work():
            try:
                with lock():url=upload(ARCHIVE)
                self.events.put(('success',url))
            except Exception as exc:self.events.put(('upload_failure',str(exc)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()

    def compare_versions(self):
        try:
            result=write_comparison(ARCHIVE,self.before.get(),self.after.get(),APP/'work/版本对比')
            os.startfile(result)
        except Exception as exc:messagebox.showerror('无法对比',str(exc))

    def open_diagnostic(self):
        if self.failed:os.startfile(self.failed)

    def close(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno('正在提取','要停止本次提取吗？上次成功的结果会保留。'):
                self.stop();self.wait_close()
        else:self.root.destroy()

    def wait_close(self):
        if self.worker and self.worker.is_alive():self.root.after(200,self.wait_close)
        else:self.root.destroy()


def main():
    import ctypes
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):pass
    root=tk.Tk();app=App(root);root.mainloop()


if __name__=='__main__':main()
