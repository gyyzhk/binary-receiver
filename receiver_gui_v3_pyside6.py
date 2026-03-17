#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
火场音频回传 PC端 V3.0 (PySide6版)
作者:一棵桔子
"""

import sys
import socket
import threading
import time
import os
import wave
import subprocess
import struct
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QTextEdit, QListWidget, QSlider, QFrame,
                               QGroupBox, QComboBox, QProgressBar, QMessageBox,
                               QFileDialog, QListWidgetItem)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QColor, QFont

# 全局配置
SERVER_PORT = 119
SAMPLE_RATE = 16000
CHANNELS = 1
BITS_PER_SAMPLE = 16
SILENCE_THRESHOLD = 500
SILENCE_DURATION = 3
BUFFER_SIZE = 4096


class AudioReceiver(QMainWindow):
    """音频接收主窗口"""
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.server_socket = None
        self.clients = {}  # {addr: {'device_id': xxx, 'frames': xxx}}
        self.clients_lock = threading.Lock()
        self.audio_buffer = {}
        self.buffer_lock = threading.Lock()
        
        # 监听相关
        self.monitoring = False
        self.monitor_device = None
        self.monitor_thread = None
        
        self.init_ui()
        
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("火场音频回传 V3.0")
        self.setGeometry(100, 100, 900, 700)
        
        # 中央窗口
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # ===== 标题栏 =====
        title_label = QLabel("🎙️ 火场音频回传 PC端")
        title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #1a1a2e;
            padding: 10px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 版本信息
        version_label = QLabel("作者:一棵桔子  |  版本:V3.0 (PySide6版)")
        version_label.setStyleSheet("color: #666; font-size: 12px;")
        version_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(version_label)
        
        main_layout.addSpacing(10)
        
        # ===== 服务器配置区域 =====
        server_group = QGroupBox("服务器配置")
        server_layout = QHBoxLayout()
        
        server_layout.addWidget(QLabel("端口:"))
        self.port_entry = QLineEdit(str(SERVER_PORT))
        self.port_entry.setMaximumWidth(100)
        server_layout.addWidget(self.port_entry)
        
        self.start_btn = QPushButton("启动服务")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
        """)
        self.start_btn.clicked.connect(self.start_server)
        server_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("停止服务")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #da190b; }
        """)
        self.stop_btn.clicked.connect(self.stop_server)
        server_layout.addWidget(self.stop_btn)
        
        self.status_label = QLabel("未启动")
        self.status_label.setStyleSheet("color: #666; font-weight: bold;")
        server_layout.addWidget(QLabel("状态:"))
        server_layout.addWidget(self.status_label)
        
        server_layout.addStretch()
        server_group.setLayout(server_layout)
        main_layout.addWidget(server_group)
        
        # ===== 连接设备列表 =====
        device_group = QGroupBox("已连接设备")
        device_layout = QVBoxLayout()
        
        self.device_list = QListWidget()
        self.device_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
            }
        """)
        device_layout.addWidget(self.device_list)
        device_group.setLayout(device_layout)
        main_layout.addWidget(device_group, 1)
        
        # ===== 实时监听区域 =====
        monitor_group = QGroupBox("实时监听")
        monitor_layout = QVBoxLayout()
        
        # 监听控制行
        monitor_top = QHBoxLayout()
        monitor_top.addWidget(QLabel("选择设备:"))
        
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(200)
        monitor_top.addWidget(self.device_combo)
        
        self.monitor_btn = QPushButton("开始监听")
        self.monitor_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 6px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1976D2; }
        """)
        self.monitor_btn.clicked.connect(self.toggle_monitor)
        monitor_top.addWidget(self.monitor_btn)
        
        self.monitor_status = QLabel("未监听")
        self.monitor_status.setStyleSheet("color: #666;")
        monitor_top.addWidget(self.monitor_status)
        
        monitor_top.addStretch()
        monitor_layout.addLayout(monitor_top)
        
        # 音量条
        self.volume_bar = QProgressBar()
        self.volume_bar.setMaximum(2000)
        self.volume_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        monitor_layout.addWidget(QLabel("音量:"))
        monitor_layout.addWidget(self.volume_bar)
        
        monitor_group.setLayout(monitor_layout)
        main_layout.addWidget(monitor_group)
        
        # ===== 日志区域 =====
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #1e1e1e;
                color: #0f0;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # ===== 已接收文件区域 =====
        files_group = QGroupBox("已接收文件")
        files_layout = QVBoxLayout()
        
        files_top = QHBoxLayout()
        
        self.files_list = QListWidget()
        self.files_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 5px;
            }
        """)
        files_layout.addWidget(self.files_list)
        
        files_btn_layout = QVBoxLayout()
        
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.load_received_files)
        files_btn_layout.addWidget(refresh_btn)
        
        open_folder_btn = QPushButton("📂 打开文件夹")
        open_folder_btn.clicked.connect(self.open_received_folder)
        files_btn_layout.addWidget(open_folder_btn)
        
        files_top.addLayout(files_btn_layout)
        files_top.addWidget(self.files_list, 1)
        
        files_layout.addLayout(files_top)
        files_group.setLayout(files_layout)
        main_layout.addWidget(files_group, 1)
        
        # 加载已有文件
        self.load_received_files()
        
    def log(self, msg):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
        
    def start_server(self):
        """启动服务器"""
        global SERVER_PORT
        
        try:
            SERVER_PORT = int(self.port_entry.text())
        except:
            QMessageBox.warning(self, "错误", "端口必须是数字")
            return
        
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', SERVER_PORT))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1)
            
            # 获取本机IP
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
            except:
                local_ip = "127.0.0.1"
            
            self.running = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText("运行中")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            
            self.log(f"服务器启动 - IP: {local_ip}, 端口: {SERVER_PORT}")
            
            # 启动接受连接的线程
            self.accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
            self.accept_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动失败: {e}")
            
    def stop_server(self):
        """停止服务器"""
        self.running = False
        
        # 关闭所有客户端连接
        with self.clients_lock:
            for addr in list(self.clients.keys()):
                try:
                    self.clients[addr]['socket'].close()
                except:
                    pass
            self.clients.clear()
        
        # 关闭服务器socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("未启动")
        self.status_label.setStyleSheet("color: #666;")
        
        self.log("服务器已停止")
        self.update_device_list()
        
    def accept_connections(self):
        """接受客户端连接"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                
                # 启动接收线程
                recv_thread = threading.Thread(
                    target=self.receive_audio, 
                    args=(client_socket, addr),
                    daemon=True
                )
                recv_thread.start()
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.log(f"接受连接错误: {e}")
                break
                
    def receive_audio(self, client_socket, addr):
        """接收客户端音频"""
        device_id = None
        
        try:
            # 接收设备ID (64字节)
            device_id_data = client_socket.recv(64)
            if device_id_data:
                device_id = device_id_data.decode('utf-8').strip('\x00')
                if not device_id:
                    device_id = f"device_{addr[0]}_{addr[1]}"
                    
                with self.clients_lock:
                    self.clients[addr] = {
                        'socket': client_socket,
                        'device_id': device_id,
                        'frames': 0
                    }
                
                self.log(f"设备连接: {device_id} ({addr[0]})")
                self.update_device_list()
                
                # 持续接收音频数据
                while self.running:
                    try:
                        # 接收4字节长度 + 音频数据
                        header = client_socket.recv(4)
                        if not header:
                            break
                        
                        length = struct.unpack('I', header)[0]
                        
                        # 分片接收
                        audio_data = b''
                        while len(audio_data) < length:
                            chunk = client_socket.recv(length - len(audio_data))
                            if not chunk:
                                break
                            audio_data += chunk
                        
                        if audio_data:
                            # 存储到缓冲区
                            with self.buffer_lock:
                                if device_id not in self.audio_buffer:
                                    self.audio_buffer[device_id] = []
                                self.audio_buffer[device_id].append(audio_data)
                            
                            # 写入文件
                            self.save_audio(device_id, audio_data)
                            
                            # 更新计数
                            with self.clients_lock:
                                if addr in self.clients:
                                    self.clients[addr]['frames'] += 1
                                    
                    except ConnectionResetError:
                        break
                    except Exception as e:
                        if self.running:
                            pass
                        break
                        
        except Exception as e:
            self.log(f"接收音频错误: {e}")
            
        finally:
            # 断开连接
            with self.clients_lock:
                if addr in self.clients:
                    del self.clients[addr]
                    
            with self.buffer_lock:
                if device_id and device_id in self.audio_buffer:
                    del self.audio_buffer[device_id]
                    
            try:
                client_socket.close()
            except:
                pass
                
            if device_id:
                self.log(f"设备断开: {device_id}")
                self.update_device_list()
                
    def save_audio(self, device_id, audio_data):
        """保存音频到文件"""
        # 简化版：直接保存WAV
        try:
            received_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received', device_id)
            os.makedirs(received_dir, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{device_id}_{timestamp}.wav"
            filepath = os.path.join(received_dir, filename)
            
            # 写入WAV文件
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(BITS_PER_SAMPLE // 8)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_data)
                
        except Exception as e:
            self.log(f"保存音频错误: {e}")
            
    def update_device_list(self):
        """更新设备列表"""
        self.device_list.clear()
        self.device_combo.clear()
        
        with self.clients_lock:
            for addr, info in self.clients.items():
                device_id = info['device_id']
                self.device_list.addItem(f"{device_id} ({addr[0]})")
                self.device_combo.addItem(device_id)
                
    def toggle_monitor(self):
        """切换监听状态"""
        if self.monitoring:
            # 停止监听
            self.monitoring = False
            self.monitor_btn.setText("开始监听")
            self.monitor_status.setText("未监听")
            self.log("监听已停止")
        else:
            # 开始监听
            selected = self.device_combo.currentText()
            if not selected:
                QMessageBox.warning(self, "提示", "请先选择要监听的设备")
                return
            
            # 检查设备是否在线
            device_online = False
            with self.clients_lock:
                for addr, info in self.clients.items():
                    if info['device_id'] == selected:
                        device_online = True
                        break
            
            if not device_online:
                QMessageBox.warning(self, "提示", "设备已离线，请重新选择")
                return
            
            self.monitoring = True
            self.monitor_device = selected
            self.monitor_btn.setText("停止监听")
            self.monitor_status.setText(f"监听中: {selected}")
            self.log(f"开始监听: {selected}")
            
            # 启动监听线程
            if self.monitor_thread is None or not self.monitor_thread.is_alive():
                self.monitor_thread = threading.Thread(target=self.monitor_audio, daemon=True)
                self.monitor_thread.start()
                
    def monitor_audio(self):
        """监听音频流"""
        import pygame
        
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=CHANNELS, buffer=512)
        except:
            pass
        
        while self.monitoring:
            try:
                time.sleep(0.1)
            except:
                break
                
    def load_received_files(self):
        """加载已接收文件"""
        self.files_list.clear()
        
        received_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received')
        if not os.path.exists(received_dir):
            return
        
        # 收集所有文件及修改时间
        file_list = []
        for device_id in os.listdir(received_dir):
            device_dir = os.path.join(received_dir, device_id)
            if os.path.isdir(device_dir):
                for filename in os.listdir(device_dir):
                    if filename.endswith('.mp3') or filename.endswith('.wav'):
                        filepath = os.path.join(device_dir, filename)
                        mtime = os.path.getmtime(filepath)
                        file_list.append((mtime, filepath, device_id, filename))
        
        # 按修改时间倒序
        file_list.sort(key=lambda x: x[0], reverse=True)
        
        for mtime, filepath, device_id, filename in file_list:
            size = os.path.getsize(filepath)
            self.files_list.addItem(f"{device_id}/{filename} ({size/1024:.1f}KB)")
            
    def open_received_folder(self):
        """打开接收文件夹"""
        received_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'received')
        if os.path.exists(received_dir):
            os.startfile(received_dir)


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    window = AudioReceiver()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
