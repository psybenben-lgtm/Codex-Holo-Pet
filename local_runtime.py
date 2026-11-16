# -*- coding: utf-8 -*-
"""
本地运行环境与端口统一配置中心 (local_runtime.py)
用途：
1. 统一管理本地 HTTP / HTTPS / UDP 端口，彻底规避旧端口 8765 与 18765。
2. 统一提供绕过本地代理 (ProxyHandler({})) 的 urllib opener，避免受系统 HTTP_PROXY/10808 代理干扰。
3. 供服务端、桌面透明层、旧版桌宠客户端、向导生成器和自动化测试统一调用。
"""
import os
from urllib.request import ProxyHandler, build_opener

# 硬性禁用的历史端口，绝不监听或主动调用
FORBIDDEN_PORTS = frozenset({8765, 18765})

# 本套交付包默认本地端口（避开 8765 / 18765 及其他工具常用端口）
DEFAULT_HTTP_PORT = 29765
DEFAULT_HTTPS_PORT = 29766
DEFAULT_UDP_PORT = 29767


def _parse_safe_port(env_names, fallback_port):
    if isinstance(env_names, str):
        env_names = (env_names,)
    for env_name in env_names:
        raw = os.environ.get(env_name, '').strip()
        if raw:
            try:
                port = int(raw)
                if 1024 <= port <= 65535 and port not in FORBIDDEN_PORTS:
                    return port
            except ValueError:
                pass
    return fallback_port


def get_http_port():
    """获取当前配置的安全 HTTP 端口（默认 29765，绝不返回 8765 / 18765）。"""
    return _parse_safe_port(('CODEX_HOLO_PORT', 'HOLO_HTTP_PORT'), DEFAULT_HTTP_PORT)


def get_https_port():
    """获取当前配置的安全 HTTPS 端口（默认 29766）。"""
    env_https = _parse_safe_port(('CODEX_HOLO_HTTPS_PORT', 'HOLO_HTTPS_PORT'), 0)
    if env_https:
        return env_https
    http_port = get_http_port()
    https_port = http_port + 1
    if https_port in FORBIDDEN_PORTS:
        https_port += 1
    return https_port


def get_udp_port():
    """获取局域网 UDP 发现端口（默认 29767）。"""
    return _parse_safe_port(('CODEX_HOLO_UDP_PORT', 'HOLO_UDP_PORT'), DEFAULT_UDP_PORT)


def get_local_host_url(port=None):
    """返回本机回环访问地址。"""
    p = port if port and port not in FORBIDDEN_PORTS else get_http_port()
    return f'http://127.0.0.1:{p}'


def get_no_proxy_opener():
    """构造禁用所有 HTTP/HTTPS 代理的 urllib opener，防止本地回环请求被系统代理拦截。"""
    return build_opener(ProxyHandler({}))
