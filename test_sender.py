#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import wave
import os
import sys
import time

def send_audio_file(server_ip, server_port, device_id, wav_file):
    """发送WAV音频文件到服务器"""
    
    if not os.path.exists(wav_file):
        print(f"文件不存在: {wav_file}")
        return False
    
    print(f"连接到 {server_ip}:{server_port}...")
    
    try:
        # 创建socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((server_ip, server_port))
        print("已连接")
        
        # 发送握手
        handshake = f"BINARY|{device_id}"
        handshake_bytes = handshake.encode('utf-8').ljust(64, b'\x00')
        sock.send(handshake_bytes)
        print(f"握手已发送: {handshake}")
        
        # 打开WAV文件
        wf = wave.open(wav_file, 'rb')
        
        # 读取音频参数
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        
        print(f"WAV信息: {channels}通道, {sample_width}字节/样本, {frame_rate}Hz")
        
        # 发送音频数据
        total_sent = 0
        chunk_size = 4096
        
        while True:
            data = wf.readframes(chunk_size)
            if not data:
                break
            
            sock.send(data)
            total_sent += len(data)
            print(f"已发送: {total_sent / 1024:.1f} KB", end='\r')
        
        wf.close()
        print(f"\n发送完成! 总计: {total_sent / 1024:.1f} KB")
        
        # 等待一下让服务器处理
        time.sleep(1)
        
        sock.close()
        print("连接关闭")
        return True
        
    except Exception as e:
        print(f"错误: {e}")
        return False

def list_audio_files(folder):
    """列出文件夹中的WAV文件"""
    if not os.path.exists(folder):
        print(f"文件夹不存在: {folder}")
        return []
    
    files = [f for f in os.listdir(folder) if f.endswith('.wav')]
    return sorted(files)

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='发送音频到二进制接收端')
    parser.add_argument('--ip', default='127.0.0.1', help='服务器IP')
    parser.add_argument('--port', type=int, default=8080, help='服务器端口')
    parser.add_argument('--device', default='test_pc', help='设备ID')
    parser.add_argument('--file', help='WAV文件路径')
    parser.add_argument('--folder', help='WAV文件夹路径（会列出文件供选择）')
    
    args = parser.parse_args()
    
    if args.folder:
        files = list_audio_files(args.folder)
        if not files:
            print("文件夹中没有WAV文件")
            sys.exit(1)
        
        print("可用文件:")
        for i, f in enumerate(files):
            print(f"  {i+1}. {f}")
        
        try:
            choice = int(input("\n选择文件编号: ")) - 1
            if 0 <= choice < len(files):
                file_path = os.path.join(args.folder, files[choice])
            else:
                print("无效选择")
                sys.exit(1)
        except ValueError:
            print("无效输入")
            sys.exit(1)
    elif args.file:
        file_path = args.file
    else:
        print("请指定 --file 或 --folder")
        parser.print_help()
        sys.exit(1)
    
    send_audio_file(args.ip, args.port, args.device, file_path)
