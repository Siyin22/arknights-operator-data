"""Versioned offline pipeline. Only verified runs become the latest result."""
import argparse
import contextlib
import datetime
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import zipfile
from pathlib import Path
from common import APP, OUTPUT, ARCHIVE, VERSION, game_files, read_json, write_json, sha256
from archive_store import save_run, verified_current


class Cancelled(Exception): pass


def check_client(game):
    paths = game_files(game)
    for p in paths.values():
        if not p.is_file(): raise ValueError(f'未找到游戏文件：{p.name}。请选择包含 Arknights.exe 的安装目录。')
    with paths['metadata'].open('rb') as f: head=f.read(272)
    if len(head)!=272 or struct.unpack_from('<II',head)!=(0xFAB11BAF,29):
        raise ValueError('客户端元数据格式已改变，需要适配。')
    offset,size=struct.unpack_from('<II',head,160)
    if size%92 or offset+size>paths['metadata'].stat().st_size:
        raise ValueError('客户端类型记录格式已改变，需要适配。')
    hashes={k:sha256(p) for k,p in paths.items()}
    support=read_json(APP/'adapters/supported.json')
    for adapter in support['clients']:
        if adapter['sha256']==hashes:return adapter,hashes
    raise ValueError('检测到尚未适配的客户端程序。普通资源热更不受此限制；请将诊断包交给 AI 适配后重试。')


@contextlib.contextmanager
def lock():
    import msvcrt
    with (APP/'pipeline.lock').open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise ValueError('另一个窗口正在提取，请等待它完成。')
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)


class Pipeline:
    def __init__(self, game, emit=None, cancel=None, output=None, archive=None):
        self.game=Path(game).resolve()
        self.emit=emit or (lambda msg:print(msg,flush=True))
        self.cancel=cancel or threading.Event()
        self.output=Path(output) if output else APP/'work'
        self.archive=Path(archive) if archive else ARCHIVE
        self.run_dir=None
        self.log=None
        self.stage='准备'

    def say(self,text):
        text=str(text).rstrip()
        if self.log:self.log.write(text+'\n');self.log.flush()
        self.emit(text)

    def command(self,args,timeout=600):
        if self.cancel.is_set():raise Cancelled('已取消提取；上次成功的结果保持不变。')
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUNBUFFERED']='1'
        proc=subprocess.Popen([str(x) for x in args],cwd=APP,env=env,stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW)
        lines=queue.Queue()
        def read():
            for line in proc.stdout:lines.put(line)
        thread=threading.Thread(target=read,daemon=True);thread.start()
        started=time.monotonic();tail=[]
        try:
            while proc.poll() is None or thread.is_alive() or not lines.empty():
                if self.cancel.is_set():raise Cancelled('已取消提取；上次成功的结果保持不变。')
                if time.monotonic()-started>timeout:raise TimeoutError(f'{self.stage} 超时，请查看诊断包。')
                try:line=lines.get(timeout=.1)
                except queue.Empty:continue
                tail.append(line.strip());tail=tail[-12:];self.say(line)
            if proc.returncode:raise RuntimeError(f'{self.stage}失败：\n'+'\n'.join(tail))
        finally:
            if proc.poll() is None:
                subprocess.run(['taskkill.exe','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=15)
            proc.wait(timeout=15);proc.stdout.close();thread.join(timeout=2)

    def python(self,script,*args,timeout=600):
        self.command([APP/'.venv/Scripts/python.exe',APP/'src'/script,*args],timeout)

    def step(self,title):
        self.stage=title;self.say('\n'+title)

    def diagnostics(self,error):
        details={'tool_version':VERSION,'stage':self.stage,'error':str(error),'game':str(self.game),
                 'time':datetime.datetime.now().isoformat(),'traceback':traceback.format_exc()}
        write_json(self.run_dir/'failure.json',details)
        with zipfile.ZipFile(self.run_dir/'诊断包.zip','w',zipfile.ZIP_DEFLATED) as z:
            for rel in ['failure.json','input.json','运行日志.txt','raw/version.json','raw/errors.json','schemas/native-audit.json','verification/report.json']:
                p=self.run_dir/rel
                if p.exists():z.write(p,rel)
            for p in (self.run_dir/'schemas').glob('*.fbs'):z.write(p,'schemas/'+p.name)

    def run(self):
        self.output.mkdir(parents=True,exist_ok=True)
        self.run_dir=self.output/'提取临时'
        with lock():
            # Fixed tool-owned scratch directory. Resolve and check before recursive deletion.
            if self.run_dir.resolve().parent != self.output.resolve() or self.run_dir.is_symlink():
                raise ValueError('临时目录不在预期路径，停止清理。')
            if self.run_dir.exists():shutil.rmtree(self.run_dir)
            self.run_dir.mkdir()
            try:
                with (self.run_dir/'运行日志.txt').open('w',encoding='utf-8') as self.log:
                    result=self.work()
                self.log=None
                shutil.rmtree(self.run_dir)
                return result
            except Exception as exc:
                self.log=None
                self.diagnostics(exc)
                raise
            finally:self.log=None

    def work(self):
        self.step('1/7 检查游戏版本')
        # Record hashes even for an unsupported client so adaptation can identify it.
        paths=game_files(self.game)
        hashes={k:sha256(p) for k,p in paths.items() if p.exists()}
        write_json(self.run_dir/'input.json',{'tool_version':VERSION,'game':str(self.game),'sha256':hashes})
        adapter,_=check_client(self.game)
        client_match=re.search(r'\b(\d+\.\d+\.\d+)\b',adapter['label'])
        write_json(self.run_dir/'input.json',{'tool_version':VERSION,'game':str(self.game),'sha256':hashes,
                                            'client_version':client_match[1] if client_match else None})
        self.say('已识别：'+adapter['label'])
        if not shutil.which('dotnet'):raise ValueError('缺少 .NET 8 运行环境，请将诊断包交给 AI 处理。')
        index=self.game/'Arknights_Data/PersistentData/Bundles/hot_update_list.json'
        if not index.exists():index=self.game/'Arknights_Data/StreamingAssets/AB/Windows/hot_update_list.json'
        initial_index_hash=sha256(index)
        initial_stats={k:(p.stat().st_size,p.stat().st_mtime_ns) for k,p in paths.items()}
        if (self.archive/'version.json').is_file():
            current=verified_current(self.archive)
            if (current['version']['resource_version']==read_json(index)['versionId']
                    and all('baseSkills' in p for p in current['operators'].values())):
                from version_compare import version_label
                self.say(version_label(current['version'])+' 已保存；资源版本未变，跳过重复提取。')
                return self.archive
        self.step('2/7 提取当前版本资源')
        self.python('extract.py',self.game,self.run_dir/'raw','--operators-only',timeout=900)
        self.step('3/7 从客户端恢复数据结构')
        dump=self.run_dir/'analysis';dump.mkdir()
        self.command(['dotnet',APP/'tools/Il2CppDumper-patched/Il2CppDumper.dll',paths['binary'],paths['metadata'],dump],timeout=300)
        if not (dump/'dump.cs').exists() or not (dump/'DummyDll/Assembly-CSharp.dll').exists():
            raise RuntimeError('客户端结构恢复不完整，需要适配。')
        types=dump/'types.json'
        self.command(['dotnet',APP/'tools/TypeExport/bin/Release/net8.0/TypeExport.dll',dump/'DummyDll',types],timeout=180)
        self.step('4/7 自行生成数据格式')
        self.python('schema.py',types,self.run_dir/'schemas','--binary',paths['binary'],'--dump',dump/'dump.cs',timeout=180)
        self.step('5/7 解析干员、战斗技能、后勤技能和模组')
        self.python('decode.py',self.run_dir/'schemas/schema.json',self.run_dir/'raw',self.run_dir/'json','--operators-only',timeout=600)
        self.step('6/7 核验导出结果')
        self.python('verify.py',self.run_dir,APP/'tools/flatc/flatc.exe','--operators-only',timeout=600)
        self.step('7/7 保存官方版本与差异报告')
        if self.cancel.is_set():raise Cancelled('已取消提取。')
        if sha256(index)!=initial_index_hash or any((p.stat().st_size,p.stat().st_mtime_ns)!=initial_stats[k] for k,p in paths.items()):
            raise ValueError('提取期间游戏发生更新。请等待游戏更新完成后重新提取。')
        saved=save_run(self.run_dir,self.archive)
        self.say('官方版本 '+saved['version']+' 已保存到 Git；提取中间文件将自动清理。')
        return self.archive


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('game',type=Path);a=ap.parse_args()
    try:Pipeline(a.game).run()
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
