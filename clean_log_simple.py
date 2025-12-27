#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克日志简单清理脚本
功能：当日志文件超过10MB时清空内容，不备份，不删除文件
"""

import os
import sys
from datetime import datetime

def clean_log_simple(log_path="quark_save.log", max_size_mb=10):
    """
    简单清理日志：超过指定大小就清空内容
    
    参数:
        log_path: 日志文件路径
        max_size_mb: 触发清理的最大文件大小(MB)，默认10MB
    """
    print(f"开始检查日志文件: {log_path}")
    
    # 检查文件是否存在
    if not os.path.exists(log_path):
        print(f"警告: 日志文件不存在: {log_path}")
        return False
    
    try:
        # 获取文件大小
        file_size = os.path.getsize(log_path)
        file_size_mb = file_size / (1024 * 1024)
        
        print(f"文件大小: {file_size_mb:.2f} MB")
        print(f"阈值: {max_size_mb} MB")
        
        # 检查文件大小是否超过阈值
        if file_size_mb < max_size_mb:
            print(f"文件大小 ({file_size_mb:.2f} MB) 小于阈值 ({max_size_mb} MB)，跳过清理")
            return False
        
        # 记录清理前的信息
        print(f"文件超过 {max_size_mb} MB，开始清空内容...")
        
        # 清空文件内容，保留文件
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"# 日志文件于 {datetime.now()} 被清理\n")
            f.write(f"# 原文件大小: {file_size_mb:.2f} MB\n")
            f.write(f"# 清理阈值: {max_size_mb} MB\n")
        
        print(f"成功清空日志文件: {log_path}")
        print(f"清理后文件大小: {os.path.getsize(log_path) / (1024 * 1024):.2f} MB")
        return True
        
    except Exception as e:
        print(f"清理日志文件时出错: {e}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("夸克日志简单清理脚本")
    print("功能: 当日志文件超过10MB时清空内容")
    print("=" * 50)
    
    # 使用默认参数
    success = clean_log_simple()
    
    if success:
        print("清理完成")
    else:
        print("未执行清理操作")
    
    print("脚本执行完毕")

if __name__ == "__main__":
    main()
