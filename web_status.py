# -*- coding: utf-8 -*-
"""
二进制回传 - 网页状态显示
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import os

# 全局状态
clients = {}
clients_lock = threading.Lock()


def update_client(addr, device_id):
    """更新客户端状态"""
    with clients_lock:
        clients[addr] = {
            'device_id': device_id,
            'time': time.strftime('%H:%M:%S')
        }


class StatusHandler(BaseHTTPRequestHandler):
    """HTTP请求处理"""
    
    def log_message(self, format, *args):
        pass
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(self.get_html().encode('utf-8'))
        elif self.path == '/status':
            self.handle_status()
        elif self.path == '/clients':
            self.handle_clients()
        else:
            self.send_error(404)
    
    def get_html(self):
        return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>二进制回传 - 状态监控</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #fff; padding: 20px; }
        h1 { color: #00d4ff; }
        .card { background: rgba(255,255,255,0.1); padding: 15px; margin: 10px 0; border-radius: 8px; }
        .info { color: #888; }
    </style>
</head>
<body>
    <h1>🎙️ 二进制回传 v1.0.1</h1>
    <div class="card">
        <h3>连接状态</h3>
        <p class="info" id="status">等待连接...</p>
    </div>
    <div class="card">
        <h3>已连接设备</h3>
        <div id="clients">-</div>
    </div>
    <script>
        function update() {
            fetch('/clients').then(r => r.json()).then(data => {
                document.getElementById('status').textContent = 
                    data.count + ' 个设备连接中';
                let html = '';
                data.clients.forEach(c => {
                    html += '<p>' + c.device_id + ' - ' + c.time + '</p>';
                });
                document.getElementById('clients').innerHTML = html || '无';
            });
        }
        setInterval(update, 2000);
        update();
    </script>
</body>
</html>'''
    
    def handle_status(self):
        with clients_lock:
            count = len(clients)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'connected': count > 0, 'count': count}).encode())
    
    def handle_clients(self):
        with clients_lock:
            client_list = [{'device_id': v['device_id'], 'time': v['time']} for v in clients.values()]
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'count': len(client_list), 'clients': client_list}).encode())


class WebServer:
    """网页服务器"""
    
    def __init__(self, port=8888):
        self.port = port
        self.server = None
    
    def start(self):
        self.server = HTTPServer(('0.0.0.0', self.port), StatusHandler)
        print(f"网页服务启动: http://localhost:{self.port}")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


import time
