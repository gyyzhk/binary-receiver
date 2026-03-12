#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import socket
import struct
import wave
import os
import datetime
import subprocess
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import pygame
import shutil

# 全局变量
SERVER_PORT = 8080
WEB_PORT = 8888

# 音频参数
SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16

# 静音分割设置
SILENCE_THRESHOLD = 500  # 静音阈值
SILENCE_DURATION = 3  # 静音3秒则分段

class AudioReceiverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("火场音频回传 PC接收端 v2.3")
        self.root.geometry("900x700")
        
        # 状态变量
        self.running = False
        self.server_socket = None
        self.clients = {}  # {addr: {'device_id': xxx, 'file': xxx, 'start_time': xxx, 'silent_time': 0}}
        self.received_files = []
        
        # 音量数据（用于图表）
        self.volume_data = []
        
        # 初始化pygame（用于播放）
        try:
            pygame.mixer.init()
        except:
            pass
        
        self.create_ui()
        self.load_received_files()
        
    def create_ui(self):
        # 顶部状态栏
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 作者版本信息
        info_frame = ttk.Frame(top_frame)
        info_frame.grid(row=0, column=0, columnspan=8, sticky=tk.W)
        ttk.Label(info_frame, text="作者:一棵桔子  |  版本:V2.3", foreground="blue", font=('Arial', 10)).pack(side=tk.LEFT)
        
        # 服务器状态
        ttk.Label(top_frame, text="服务器状态:").grid(row=1, column=0, sticky=tk.W)
        self.status_label = ttk.Label(top_frame, text="未启动", foreground="red", font=('Arial', 12, 'bold'))
        self.status_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        # 端口设置
        ttk.Label(top_frame, text="端口:").grid(row=1, column=2, sticky=tk.W, padx=(20,0))
        self.port_entry = ttk.Entry(top_frame, width=8)
        self.port_entry.insert(0, str(SERVER_PORT))
        self.port_entry.grid(row=1, column=3, sticky=tk.W, padx=5)
        
        # 静音阈值设置
        ttk.Label(top_frame, text="静音阈值:").grid(row=1, column=4, sticky=tk.W, padx=(20,0))
        self.silence_entry = ttk.Entry(top_frame, width=6)
        self.silence_entry.insert(0, str(SILENCE_THRESHOLD))
        self.silence_entry.grid(row=1, column=5, sticky=tk.W, padx=5)
        
        # 控制按钮
        self.start_btn = ttk.Button(top_frame, text="启动服务", command=self.start_server, width=12)
        self.start_btn.grid(row=1, column=6, sticky=tk.W, padx=20)
        
        self.stop_btn = ttk.Button(top_frame, text="停止服务", command=self.stop_server, state=tk.DISABLED, width=12)
        self.stop_btn.grid(row=1, column=7, sticky=tk.W)
        
        # ===== 音量显示 =====
        volume_frame = ttk.LabelFrame(self.root, text="实时音量", padding=5)
        volume_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.volume_canvas = tk.Canvas(volume_frame, height=80, bg='black')
        self.volume_canvas.pack(fill=tk.X)
        
        # ===== 主界面：设备列表 + 文件列表 =====
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左侧：在线设备
        device_frame = ttk.LabelFrame(main_frame, text="在线设备", padding=5)
        device_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))
        
        self.devices_listbox = tk.Listbox(device_frame, height=10)
        self.devices_listbox.pack(fill=tk.BOTH, expand=True)
        
        # 设备详情
        device_info_frame = ttk.Frame(device_frame)
        device_info_frame.pack(fill=tk.X, pady=5)
        
        self.device_volume_label = ttk.Label(device_info_frame, text="音量: 0", foreground='green')
        self.device_volume_label.pack(side=tk.LEFT)
        
        self.device_status_label = ttk.Label(device_info_frame, text="状态: 等待中...", foreground='gray')
        self.device_status_label.pack(side=tk.RIGHT)
        
        # 右侧：已接收文件
        files_frame = ttk.LabelFrame(main_frame, text="已接收文件", padding=5)
        files_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5,0))
        
        # 工具栏
        toolbar = ttk.Frame(files_frame)
        toolbar.pack(fill=tk.X)
        
        ttk.Button(toolbar, text="刷新", command=self.load_received_files, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="播放", command=self.play_selected_file, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="打开文件夹", command=self.open_folder, width=12).pack(side=tk.RIGHT, padx=2)
        
        self.files_listbox = tk.Listbox(files_frame)
        self.files_listbox.pack(fill=tk.BOTH, expand=True)
        self.files_listbox.bind('<Double-Button-1>', lambda e: self.play_selected_file())
        
        # ===== 日志显示 =====
        log_frame = ttk.LabelFrame(self.root, text="接收日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 音量更新定时器
        self.update_volume_display()
        
    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def start_server(self):
        global SERVER_PORT, SILENCE_THRESHOLD, SILENCE_DURATION
        
        try:
            SERVER_PORT = int(self.port_entry.get())
            SILENCE_THRESHOLD = int(self.silence_entry.get())
        except:
            messagebox.showerror("错误", "端口和阈值必须是数字")
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', SERVER_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1)
            
            self.running = True
            
            # 启动接受连接线程
            self.accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.accept_thread.start()
            
            # 启动网页服务
            self.web_thread = threading.Thread(target=self.start_web_server, daemon=True)
            self.web_thread.start()
            
            self.status_label.config(text="运行中", foreground="green")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            self.log(f"服务器启动 - 端口 {SERVER_PORT}")
            self.log(f"静音阈值: {SILENCE_THRESHOLD}")
            
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {e}")
            self.log(f"启动失败: {e}")
    
    def stop_server(self):
        self.running = False
        
        # 关闭所有客户端
        for addr, info in list(self.clients.items()):
            try:
                if info.get('file'):
                    info['file'].close()
                info['sock'].close()
            except:
                pass
        self.clients.clear()
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        self.status_label.config(text="已停止", foreground="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        self.update_devices_list()
        self.log("服务器已停止")
    
    def accept_connections(self):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                client_sock.settimeout(30)
                
                # 接收握手
                try:
                    handshake = client_sock.recv(64)
                    if handshake:
                        raw_device_id = handshake.decode('utf-8', errors='ignore').strip('\x00')
                        if '|' in raw_device_id:
                            raw_device_id = raw_device_id.split('|', 1)[1]
                        device_id = ''.join(c if c.isalnum() or c in '_-' else '_' for c in raw_device_id)
                        
                        self.log(f"新设备连接: {device_id} ({addr[0]})")
                        
                        # 创建音频文件
                        device_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received', device_id)
                        os.makedirs(device_dir, exist_ok=True)
                        
                        client_info = {
                            'sock': client_sock,
                            'addr': addr,
                            'device_id': device_id,
                            'file': None,
                            'file_path': None,
                            'start_time': time.time(),
                            'silent_time': 0,
                            'last_volume': 0
                        }
                        self.clients[addr] = client_info
                        
                        # 启动接收线程
                        recv_thread = threading.Thread(target=self.receive_audio, args=(addr,), daemon=True)
                        recv_thread.start()
                        
                except Exception as e:
                    self.log(f"握手失败: {e}")
                    client_sock.close()
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log(f"接受连接错误: {e}")
                break
        
        self.update_devices_list()
    
    def receive_audio(self, addr):
        global SILENCE_THRESHOLD, SILENCE_DURATION
        
        client_info = self.clients.get(addr)
        if not client_info:
            return
            
        device_id = client_info['device_id']
        sock = client_info['sock']
        
        device_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received', device_id)
        os.makedirs(device_dir, exist_ok=True)
        
        buffer_size = 4096
        is_recording = False  # 是否正在录音
        wf = None
        filepath = None
        total_bytes = 0
        header_skipped = False
        silent_time = 0
        
        while self.running:
            try:
                data = sock.recv(buffer_size)
                if not data:
                    break
                
                # 跳过WAV头
                if not header_skipped and len(data) >= 44:
                    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
                        data = data[44:]
                    header_skipped = True
                
                if len(data) > 0:
                    # 计算音量
                    volume = self.calculate_rms(data)
                    client_info['last_volume'] = volume
                    
                    if volume > SILENCE_THRESHOLD:
                        # 有声音
                        if not is_recording:
                            # 开始新录音
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"audio_{timestamp}.wav"
                            filepath = os.path.join(device_dir, filename)
                            wf = wave.open(filepath, 'wb')
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(BITS_PER_SAMPLE // 8)
                            wf.setframerate(SAMPLE_RATE)
                            is_recording = True
                            total_bytes = 0
                            self.log(f"[{device_id}] 开始录音...")
                        
                        if wf:
                            wf.writeframes(data)
                            total_bytes += len(data)
                        
                        silent_time = 0
                    else:
                        # 静音
                        if is_recording:
                            silent_time += 0.1
                            if silent_time > SILENCE_DURATION:
                                # 静音超过阈值，停止录音
                                if wf:
                                    wf.close()
                                    total_seconds = total_bytes / (SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8)
                                    if total_seconds > 0.5:  # 少于0.5秒不要
                                        self.log(f"[{device_id}] 录音完成: {os.path.basename(filepath)} ({total_seconds:.1f}秒)")
                                        
                                        # 转MP3
                                        mp3_path = filepath.replace('.wav', '.mp3')
                                        try:
                                            subprocess.run(['ffmpeg', '-i', filepath, '-y', mp3_path], 
                                                         capture_output=True, timeout=30)
                                            if os.path.exists(mp3_path):
                                                os.remove(filepath)
                                                self.log(f"[{device_id}] 已转MP3: {os.path.basename(mp3_path)}")
                                        except:
                                            pass
                                        
                                        self.load_received_files()
                                    else:
                                        # 太短，删除
                                        if filepath and os.path.exists(filepath):
                                            os.remove(filepath)
                                        self.log(f"[{device_id}] 录音太短，已丢弃")
                                    
                                    wf = None
                                    filepath = None
                                    is_recording = False
            
            except socket.timeout:
                continue
            except Exception as e:
                break
        
        # 关闭最后的文件
        if wf:
            wf.close()
            if total_bytes > 16000:  # 至少1秒
                total_seconds = total_bytes / (SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8)
                self.log(f"[{device_id}] 录音完成: {os.path.basename(filepath)} ({total_seconds:.1f}秒)")
                
                mp3_path = filepath.replace('.wav', '.mp3')
                try:
                    subprocess.run(['ffmpeg', '-i', filepath, '-y', mp3_path], 
                                 capture_output=True, timeout=30)
                    if os.path.exists(mp3_path):
                        os.remove(filepath)
                except:
                    pass
                
                self.load_received_files()
        
        # 移除客户端
        if addr in self.clients:
            del self.clients[addr]
        
        self.update_devices_list()
        self.log(f"设备断开: {device_id}")
    
    def calculate_rms(self, data):
        """计算音频RMS音量"""
        samples = []
        for i in range(0, len(data) - 1, 2):
            if i + 1 < len(data):
                sample = (data[i + 1] << 8) | (data[i] & 0xFF)
                if sample > 32767:
                    sample -= 65536
                samples.append(sample)
        
        if not samples:
            return 0
        
        rms = sum(s * s for s in samples) / len(samples)
        return int(rms ** 0.5)
    
    def update_devices_list(self):
        self.devices_listbox.delete(0, tk.END)
        for addr, info in self.clients.items():
            duration = int(time.time() - info['start_time'])
            self.devices_listbox.insert(tk.END, f"{info['device_id']} | {addr[0]} | {duration}秒")
    
    def load_received_files(self):
        self.received_files = []
        self.files_listbox.delete(0, tk.END)
        
        received_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received')
        if not os.path.exists(received_dir):
            return
        
        for device_id in os.listdir(received_dir):
            device_dir = os.path.join(received_dir, device_id)
            if os.path.isdir(device_dir):
                for filename in os.listdir(device_dir):
                    if filename.endswith('.mp3') or filename.endswith('.wav'):
                        filepath = os.path.join(device_dir, filename)
                        size = os.path.getsize(filepath)
                        self.received_files.append(filepath)
                        self.files_listbox.insert(tk.END, f"{device_id}/{filename} ({size/1024:.1f}KB)")
    
    def play_selected_file(self):
        selection = self.files_listbox.curselection()
        if selection:
            filepath = self.received_files[selection[0]]
            try:
                if filepath.endswith('.mp3'):
                    pygame.mixer.music.load(filepath)
                    pygame.mixer.music.play()
                    self.log(f"播放: {filepath}")
                else:
                    self.log("仅支持MP3文件播放")
            except Exception as e:
                self.log(f"播放失败: {e}")
    
    def open_folder(self):
        received_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received')
        if os.name == 'nt':
            os.startfile(received_dir)
        else:
            import subprocess
            subprocess.Popen(['open', received_dir])
    
    def update_volume_display(self):
        """更新音量显示"""
        if self.running:
            self.update_devices_list()
            
            # 绘制音量条
            self.volume_canvas.delete('all')
            
            if self.clients:
                # 获取最大音量
                max_vol = 0
                for addr, info in self.clients.items():
                    vol = info.get('last_volume', 0)
                    if vol > max_vol:
                        max_vol = vol
                
                # 绘制音量条
                bar_width = 800
                bar_height = 60
                
                # 音量百分比
                vol_percent = min(1.0, max_vol / 32767)
                fill_width = int(bar_width * vol_percent)
                
                # 颜色根据音量大小变化
                if vol_percent < 0.3:
                    color = 'green'
                elif vol_percent < 0.7:
                    color = 'yellow'
                else:
                    color = 'red'
                
                # 绘制音量条背景
                self.volume_canvas.create_rectangle(0, 0, bar_width, bar_height, fill='#333333', outline='')
                
                # 绘制音量条
                if fill_width > 0:
                    self.volume_canvas.create_rectangle(0, 0, fill_width, bar_height, fill=color, outline='')
                
                # 显示数值
                self.volume_canvas.create_text(10, 30, text=f"音量: {max_vol}", fill='white', anchor=tk.W, font=('Arial', 14))
                
                # 阈值线
                threshold_x = int(bar_width * (SILENCE_THRESHOLD / 32767))
                self.volume_canvas.create_line(threshold_x, 0, threshold_x, bar_height, fill='blue', width=2)
                self.volume_canvas.create_text(threshold_x+5, 30, text=f"阈值:{SILENCE_THRESHOLD}", fill='blue', anchor=tk.W)
                
                # 更新设备状态
                if self.clients:
                    info = list(self.clients.values())[0]
                    self.device_volume_label.config(text=f"音量: {info.get('last_volume', 0)}")
                    
                    if info.get('last_volume', 0) > SILENCE_THRESHOLD:
                        self.device_status_label.config(text="录音中...", foreground='green')
                    else:
                        self.device_status_label.config(text="静音等待...", foreground='gray')
            else:
                self.volume_canvas.create_text(400, 30, text="无设备连接", fill='gray', anchor=tk.CENTER, font=('Arial', 16))
                self.device_volume_label.config(text="音量: 0")
                self.device_status_label.config(text="等待连接...", foreground='gray')
        
        # 每100ms更新一次
        self.root.after(100, self.update_volume_display)
    
    def start_web_server(self):
        """启动简单的网页服务器"""
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/status':
                    clients_info = []
                    for addr, c in self.clients.items():
                        clients_info.append({
                            'device_id': c['device_id'],
                            'ip': addr[0],
                            'volume': c.get('last_volume', 0)
                        })
                    
                    response = {
                        'status': 'running' if self.running else 'stopped',
                        'count': len(self.clients),
                        'clients': clients_info
                    }
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(response).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                pass
        
        try:
            server = HTTPServer(('0.0.0.0', WEB_PORT), Handler)
            server.serve_forever()
        except:
            pass

if __name__ == '__main__':
    root = tk.Tk()
    app = AudioReceiverGUI(root)
    root.mainloop()
