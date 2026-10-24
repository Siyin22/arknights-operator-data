"""Bounded GitHub requests; proxy routing is confined to each child process."""
import os
import re
import socket
import subprocess
from pathlib import Path

from archive_store import REPOSITORY
from version_compare import git, tags


class UploadError(RuntimeError):
    pass


def proxy_available():
    try:
        with socket.create_connection(('127.0.0.1', 7897), timeout=1):
            return True
    except OSError:
        return False


def run_network(command, *, read_only=False, is_git=False, timeout=60):
    proxy = proxy_available()
    for attempt in range(2 if proxy and read_only else 1):
        use_proxy = proxy and attempt == 0
        env = os.environ.copy()
        for key in list(env):
            if key.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
                env.pop(key)
        env['NO_PROXY'] = 'localhost,127.0.0.1,::1'
        if use_proxy:
            env['HTTPS_PROXY'] = 'http://127.0.0.1:7897'
        env['GIT_TERMINAL_PROMPT'] = '0'
        cmd = list(command)
        if is_git:
            cmd[1:1] = ['-c', 'http.proxy=' + ('http://127.0.0.1:7897' if use_proxy else ''),
                        '-c', 'http.connectTimeout=10', '-c', 'http.lowSpeedLimit=1', '-c', 'http.lowSpeedTime=30']
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding='utf-8',
                                    timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except subprocess.TimeoutExpired as exc:
            if use_proxy and read_only:
                continue
            raise UploadError('GitHub 请求超时；本地版本已保留，可稍后重试上传。') from exc
        if result.returncode == 0:
            return result.stdout
        message = result.stderr.strip() or result.stdout.strip()
        if use_proxy and read_only and re.search(r'connect|resolve|TLS|SSL|timeout|timed out|EOF|reset|unreachable', message, re.I):
            continue
        raise UploadError(message or 'GitHub 操作失败')
    raise UploadError('代理和直连请求均超时。')


def configure_remote(repo):
    repo = Path(repo)
    expected = f'https://github.com/{REPOSITORY}.git'
    remotes = git(repo, 'remote').splitlines()
    if 'origin' not in remotes:
        git(repo, 'remote', 'add', 'origin', expected)
    elif git(repo, 'remote', 'get-url', 'origin').strip() in {
        'https://github.com/Siyin22/arknights-operator-data.git',
        'https://github.com/Siyin22/arknights-update-tool.git',
    }:
        # GitHub repository renamed; migrate only this tool's original URL.
        git(repo, 'remote', 'set-url', 'origin', expected)
    elif git(repo, 'remote', 'get-url', 'origin').strip() != expected:
        raise UploadError('本地仓库 origin 与指定 GitHub 仓库不一致，停止上传。')
    git(repo, 'config', 'credential.https://github.com.helper', '!gh auth git-credential')


def upload(repo):
    repo = Path(git(repo, 'rev-parse', '--show-toplevel').strip())
    configure_remote(repo)
    if git(repo, 'status', '--porcelain').strip():
        raise UploadError('仓库有未提交的修改，本次上传已停止。')
    # Source and generated data share a checkout; runtime state stays ignored.
    from archive_store import GENERATED
    allowed = (set(GENERATED) if (repo / 'version.json').is_file() else
               {'版本数据', 'src', 'tests', 'tools', 'adapters', 'README.md', '.gitignore', '.gitattributes',
                '使用说明.txt', '安装说明.txt', '启动工具.cmd', '启动工具.vbs', 'requirements.txt', 'requirements-lock.txt'})
    if git(repo, 'ls-files', '-ci', '--exclude-standard').strip():
        raise UploadError('仓库跟踪了应忽略的本地文件，请先移除再上传。')
    if any(p.split('/')[0] not in allowed for p in git(repo, 'ls-files').splitlines()):
        raise UploadError('仓库包含预期数据与工具范围之外的文件，停止上传。')
    try:
        run_network(['git', '-C', str(repo), 'push', '--atomic', 'origin', 'main', '--tags'], is_git=True, timeout=120)
    except UploadError as exc:
        raise UploadError('数据已保存在本地 Git，上传未完成。点击“重试上传”即可，无需重新提取。\n' + str(exc)) from exc
    expected = git(repo, 'rev-parse', 'HEAD').strip()
    refs = run_network(['git', '-C', str(repo), 'ls-remote', 'origin', 'refs/heads/main',
                        *['refs/tags/' + t for t in tags(repo)]], read_only=True, is_git=True)
    remote = dict((line.split()[1], line.split()[0]) for line in refs.splitlines())
    if remote.get('refs/heads/main') != expected:
        raise UploadError('远程主分支核对未通过，本地数据已保留。')
    for tag in tags(repo):
        if remote.get('refs/tags/' + tag) != git(repo, 'rev-parse', 'refs/tags/' + tag).strip():
            raise UploadError('远程版本标签核对未通过：' + tag)
    return f'https://github.com/{REPOSITORY}'
