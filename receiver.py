# -*- coding: utf-8 -*-
"""
二进制回传 - PC接收端 v1.0.1
功能：接收安卓端原始PCM数据，转换为MP3保存，提供网页状态显示
"""

import socket
import threading
import logging
import time
import os
import wave
import struct
import subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# 配置
HOST = "0.0.0.0"
PORT = 8080
WEB_PORT = 8888
BASE_DIR = "received"
SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16
HANDSHAKE_MAGIC = "BINARY"
HANDSHAKE_SIZE = 64

# 全局状态
global_clients = {}
global_clients_lock = threading.Lock()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StatusHandler(BaseHTTPRequestHandler):
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
        body { font-family: -apple-system, sans-serif; background: linear-gradient(135deg, #1a1a2e, #16213e); color: #fff; padding: 20px; }
        h1 { color: #00d4ff; }
        .card { background: rgba(255,255,255,0.05); padding: 15px; margin: 10px 0; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); }
        .status { background: #4CAF50; padding: 5px 12px; border-radius: 15px; display: inline-block; }
    </style>
</head>
<body>
    <h1>🎙️ 二进制回传 v1.0.1</h1>
    <div class="card">
        <h3>服务器状态</h3>
        <p><span class="status" id="status">运行中</span></p>
    </div>
    <div class="card">
        <h3>已连接设备</h3>
        <div id="clients">等待连接...</div>
    </div>
    <script>
        function update() {
            fetch('/status').then(r => r.json()).then(data => {
                let html = '';
                data.clients.forEach(c => {
                    html += '<p>📱 ' + c.device_id + ' - ' + c.time + '</p>';
                });
                document.getElementById('clients').innerHTML = html || '无设备连接';
            });
        }
        setInterval(update, 2000);
        update();
    </script>
</body>
</html>'''
    
    def handle_status(self):
        with global_clients_lock:
            client_list = [{'device_id': v['device_id'], 'time': v['time']} for v in global_clients.values()]
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'count': len(client_list), 'clients': client_list}).encode())


class WebServer:
    def __init__(self, port=WEB_PORT):
        self.port = port
        self.server = None
    
    def start(self):
        self.server = HTTPServer(('0.0.0.0', self.port), StatusHandler)
        logger.info(f"网页服务启动: http://localhost:{self.port}")
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


class BinaryReceiver:
    def __init__(self, port=PORT):
        self.port = port
        self.server_socket = None
        self.running = False
        self.clients = {}
        self.clients_lock = threading.Lock()
        os.makedirs(BASE_DIR, exist_ok=True)
        self.ffmpeg_available = self.check_ffmpeg()
    
    def check_ffmpeg(self):
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
            return result.returncode == 0
        except:
            return False
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, self.port))
        self.server_socket.listen(5)
        self.server_socket.settimeout(1.0)
        self.running = True
        logger.info(f"服务器启动，监听 {HOST}:{self.port}")
        logger.info(f"ffmpeg可用: {self.ffmpeg_available}")
        threading.Thread(target=self._accept_clients, daemon=True).start()
        return self
    
    def stop(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()
        logger.info("服务器已停止")
    
    def _accept_clients(self):
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                logger.info(f"新连接: {addr}")
                threading.Thread(target=self._handle_client, args=(client_socket, addr), daemon=True).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"接受连接错误: {e}")
    
    def _handle_client(self, client_socket, addr):
        device_id = None
        wav_file = None
        frames = 0
        
        try:
            client_socket.settimeout(30.0)
            handshake_data = client_socket.recv(HANDSHAKE_SIZE)
            if not handshake_data:
                return
            
            handshake = handshake_data.decode('utf-8', errors='ignore').strip('\x00')
            logger.info(f"握手数据: {handshake}")
            
            parts = handshake.split('|')
            if len(parts) >= 2 and parts[0] == HANDSHAKE_MAGIC:
                # 过滤设备ID中的非法字符
                raw_device_id = parts[1]
                # 只保留字母、数字、下划线、连字符
                device_id = ''.join(c if c.isalnum() or c in '_-' else '_' for c in raw_device_id)
                logger.info(f"设备ID (过滤后): {device_id}")
            else:
                logger.warning(f"握手协议错误: {handshake}")
                device_id = f"device_{addr[0].replace('.', '_')}"
            
            # 更新全局状态
            with global_clients_lock:
                global_clients[addr] = {'device_id': device_id, 'time': time.strftime('%H:%M:%S')}
            
            # 创建目录和文件
            device_dir = os.path.join(BASE_DIR, device_id)
            os.makedirs(device_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            wav_filename = f"audio_{timestamp}.wav"
            wav_filepath = os.path.join(device_dir, wav_filename)
            
            wav_file = wave.open(wav_filepath, 'wb')
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(BITS_PER_SAMPLE // 8)
            wav_file.setframerate(SAMPLE_RATE)
            
            logger.info(f"开始录音: {wav_filepath}")
            
            # 检测是否需要跳过WAV文件头
            header_skipped = False
            
            while self.running:
                try:
                    data = client_socket.recv(4096)
                    if not data:
                        break
                    
                    # 检测是否是WAV文件头（仅第一次接收时检查）
                    if not header_skipped and len(data) >= 44:
                        # 检查是否是WAV头
                        if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
                            # 是WAV文件，跳过44字节WAV头
                            data = data[44:]
                            header_skipped = True
                            logger.info("检测到WAV文件头，已跳过44字节")
                        else:
                            # 不是WAV头，可能是原始PCM
                            header_skipped = True
                    
                    if len(data) > 0:
                        try:
                            wav_file.writeframes(data)
                            frames += len(data)
                        except Exception as write_err:
                            logger.error(f"写入错误: {write_err}, type={type(wav_file)}")
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"接收数据错误: {e}")
                    break
        
        except Exception as e:
            logger.error(f"处理客户端错误: {e}")
        
        finally:
            if wav_file:
                wav_file.close()
                duration = frames / (SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8)
                logger.info(f"录音完成: {wav_filename}, 时长: {duration:.2f}秒")
                if self.ffmpeg_available:
                    mp3_path = wav_filepath.replace('.wav', '.mp3')
                    self.convert_to_mp3(wav_filepath, mp3_path)
            
            with global_clients_lock:
                if addr in global_clients:
                    del global_clients[addr]
            
            try:
                client_socket.close()
            except:
                pass
            
            logger.info(f"客户端断开: {addr}")
    
    def convert_to_mp3(self, wav_path, mp3_path):
        try:
            result = subprocess.run([
                'ffmpeg', '-y', '-i', wav_path,
                '-codec:a', 'libmp3lame', '-q:a', '2', mp3_path
            ], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"已转换为MP3: {mp3_path}")
                try:
                    os.remove(wav_path)
                except:
                    pass
            else:
                logger.error(f"MP3转换失败: {result.stderr}")
        except Exception as e:
            logger.error(f"MP3转换异常: {e}")


def main():
    print("=" * 50)
    print("二进制回传 PC接收端 v1.0.1")
    print("=" * 50)
    print(f"监听端口: {PORT}")
    print(f"网页端口: {WEB_PORT}")
    print(f"保存目录: {BASE_DIR}")
    print("按 Ctrl+C 停止")
    print("=" * 50)
    
    receiver = BinaryReceiver(port=PORT)
    receiver.start()
    
    web_server = WebServer(port=WEB_PORT)
    web_server.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        receiver.stop()
        print("已停止")


if __name__ == "__main__":
    main()
