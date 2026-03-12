#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import socket
import struct
import wave
import os
import datetime
import subprocess
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
from urllib.parse import urlparse
import time

# 全局变量
server_socket = None
clients = []
running = False
received_files = []

class ReceiverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("二进制回传 PC接收端 v1.0.1")
        self.root.geometry("600x500")
        
        # 顶部状态栏
        self.status_frame = ttk.Frame(root)
        self.status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(self.status_frame, text="服务器状态:").grid(row=0, column=0, sticky=tk.W)
        self.status_label = ttk.Label(self.status_frame, text="未启动", foreground="red")
        self.status_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(self.status_frame, text="端口:").grid(row=0, column=2, sticky=tk.W, padx=(20,0))
        self.port_label = ttk.Label(self.status_frame, text="8080")
        self.port_label.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        # 控制按钮
        self.btn_frame = ttk.Frame(root)
        self.btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_btn = ttk.Button(self.btn_frame, text="启动服务", command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(self.btn_frame, text="停止服务", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.open_web_btn = ttk.Button(self.btn_frame, text="打开网页", command=self.open_web_status)
        self.open_web_btn.pack(side=tk.LEFT, padx=5)
        
        # 客户端列表
        ttk.Label(root, text="已连接设备:").pack(anchor=tk.W, padx=10, pady=(10,0))
        self.clients_listbox = tk.Listbox(root, height=6)
        self.clients_listbox.pack(fill=tk.X, padx=10, pady=5)
        
        # 日志
        ttk.Label(root, text="运行日志:").pack(anchor=tk.W, padx=10, pady=(10,0))
        self.log_text = scrolledtext.ScrolledText(root, height=12, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 底部文件列表
        ttk.Label(root, text="最近接收:").pack(anchor=tk.W, padx=10, pady=(10,0))
        self.files_listbox = tk.Listbox(root, height=5)
        self.files_listbox.pack(fill=tk.X, padx=10, pady=5)
        
        # 初始化服务器线程
        self.server_thread = None
        
        self.log("准备就绪")
    
    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def start_server(self):
        global server_socket, running
        
        try:
            # 创建socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', 8080))
            server_socket.listen(5)
            server_socket.settimeout(1)
            
            running = True
            
            # 启动接受连接线程
            self.server_thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.server_thread.start()
            
            self.status_label.config(text="运行中", foreground="green")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            
            self.log("服务器已启动 - 监听端口 8080")
            
            # 检查ffmpeg
            try:
                result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
                if result.returncode == 0:
                    self.log("ffmpeg 已安装")
                else:
                    self.log("警告: ffmpeg 未安装，无法转MP3")
            except FileNotFoundError:
                self.log("警告: ffmpeg 未安装，无法转MP3")
                
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {e}")
            self.log(f"启动失败: {e}")
    
    def stop_server(self):
        global running, server_socket, clients
        
        running = False
        
        # 关闭所有客户端
        for client in clients:
            try:
                client['sock'].close()
            except:
                pass
        clients.clear()
        
        # 关闭服务器socket
        if server_socket:
            try:
                server_socket.close()
            except:
                pass
            server_socket = None
        
        self.status_label.config(text="已停止", foreground="red")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        self.clients_listbox.delete(0, tk.END)
        self.log("服务器已停止")
    
    def accept_connections(self):
        global clients, running
        
        while running:
            try:
                client_sock, addr = server_socket.accept()
                client_sock.settimeout(60)
                
                # 接收握手
                try:
                    handshake = client_sock.recv(64)
                    if handshake:
                        raw_device_id = handshake.decode('utf-8', errors='ignore').strip('\x00')
                        # 提取设备ID并过滤非法字符
                        if '|' in raw_device_id:
                            raw_device_id = raw_device_id.split('|', 1)[1]
                        device_id = ''.join(c if c.isalnum() or c in '_-' else '_' for c in raw_device_id)
                        
                        client_info = {
                            'sock': client_sock,
                            'addr': addr,
                            'device_id': device_id,
                            'file': None,
                            'start_time': time.time()
                        }
                        clients.append(client_info)
                        
                        self.root.after(0, self.update_clients_list)
                        self.root.after(0, lambda: self.log(f"新设备连接: {device_id} ({addr[0]})"))
                        
                        # 启动接收线程
                        recv_thread = threading.Thread(target=self.receive_audio, args=(client_info,), daemon=True)
                        recv_thread.start()
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"握手失败: {e}"))
                    client_sock.close()
                    
            except socket.timeout:
                continue
            except Exception as e:
                if running:
                    self.root.after(0, lambda: self.log(f"接受连接错误: {e}"))
                break
    
    def receive_audio(self, client_info):
        global clients
        
        device_id = client_info['device_id']
        sock = client_info['sock']
        
        # 创建保存目录
        save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received', device_id)
        os.makedirs(save_dir, exist_ok=True)
        
        # 创建WAV文件
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"audio_{timestamp}.wav"
        filepath = os.path.join(save_dir, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        
        client_info['file'] = wf
        
        total_bytes = 0
        last_update = time.time()
        header_skipped = False
        
        while running:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                
                # 跳过WAV文件头（前44字节）
                if not header_skipped and len(data) >= 44:
                    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
                        data = data[44:]
                        header_skipped = True
                        self.root.after(0, lambda: self.log("检测到WAV头，已跳过"))
                
                if len(data) > 0:
                    wf.writeframes(data)
                    total_bytes += len(data)
                
                # 每秒更新一次
                if time.time() - last_update > 1:
                    self.root.after(0, lambda: self.log(f"接收中 {device_id}: {total_bytes/1024:.1f} KB"))
                    last_update = time.time()
                    
            except socket.timeout:
                continue
            except Exception as e:
                break
        
        # 关闭文件
        wf.close()
        
        # 转MP3
        mp3_file = filepath.replace('.wav', '.mp3')
        try:
            subprocess.run(['ffmpeg', '-i', filepath, '-y', mp3_file], 
                         capture_output=True, timeout=30)
            if os.path.exists(mp3_file):
                os.remove(filepath)
                self.root.after(0, lambda: self.log(f"已转MP3: {filename.replace('.wav', '.mp3')}"))
                received_files.insert(0, f"{device_id}: {filename.replace('.wav', '.mp3')}")
            else:
                self.root.after(0, lambda: self.log(f"已保存: {filename}"))
                received_files.insert(0, f"{device_id}: {filename}")
        except Exception as e:
            self.root.after(0, lambda: self.log(f"已保存: {filename} (ffmpeg未安装)"))
            received_files.insert(0, f"{device_id}: {filename}")
        
        # 更新UI
        self.root.after(0, self.update_files_list)
        
        # 移除客户端
        if client_info in clients:
            clients.remove(client_info)
        
        self.root.after(0, self.update_clients_list)
        self.root.after(0, lambda: self.log(f"设备断开: {device_id}"))
    
    def update_clients_list(self):
        self.clients_listbox.delete(0, tk.END)
        for client in clients:
            self.clients_listbox.insert(tk.END, f"{client['device_id']} - {client['addr'][0]}")
    
    def update_files_list(self):
        self.files_listbox.delete(0, tk.END)
        for f in received_files[:10]:
            self.files_listbox.insert(tk.END, f)
    
    def open_web_status(self):
        import webbrowser
        webbrowser.open("http://localhost:8888")

if __name__ == '__main__':
    root = tk.Tk()
    app = ReceiverGUI(root)
    root.mainloop()
