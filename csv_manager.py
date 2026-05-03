"""
CSV 文件管理模块
负责创建、写入、轮转和清理 CSV 文件
"""

import csv                                              # CSV 文件读写
from datetime import datetime                           # 用于生成时间戳文件名
from pathlib import Path                                # 用于文件路径操作和排序


def build_headers(reg_map: dict) -> list:
    """
    构建 CSV 表头行
    :param reg_map: 变量映射字典 {地址: (类型, 名称, 描述)}
    :return: 表头列表，第一列为"时间戳"，后续为变量名
    """
    headers = ["时间戳"]                                # 第一列固定为时间戳
    for addr in sorted(reg_map.keys()):                 # 按地址顺序遍历变量
        _, name, desc = reg_map[addr]                   # 解包获取变量名和描述
        headers.append(f"{name}({desc})" if desc else name)  # 有描述则拼接，否则只用变量名
    return headers                                      # 返回完整表头列表


def build_row(timestamp: str, values: dict, reg_map: dict, fmt_func) -> list:
    """
    构建一行 CSV 数据
    :param timestamp: 时间戳字符串
    :param values:    解析后的值字典 {地址: 值}
    :param reg_map:   变量映射字典
    :param fmt_func:  格式化函数，用于将值转为字符串
    :return: 一行数据列表
    """
    row = [timestamp]                                   # 第一列为时间戳
    for addr in sorted(reg_map.keys()):                 # 按地址顺序遍历变量
        dtype = reg_map[addr][0]                        # 获取该变量的数据类型
        row.append(fmt_func(dtype, values.get(addr)))   # 格式化值并添加到行中
    return row                                          # 返回完整数据行


def cleanup_old_files(max_keep: int):
    """
    删除旧 CSV 文件，只保留最新的 max_keep 个
    :param max_keep: 最多保留的文件数量
    """
    files = sorted(                                     # 获取所有 CSV 文件并按修改时间排序
        Path(".").glob("data_log_*.csv"),               # 匹配 data_log_*.csv 模式
        key=lambda f: f.stat().st_mtime                 # 按文件修改时间排序（旧的在前）
    )
    while len(files) > max_keep:                        # 如果文件数量超过上限
        files.pop(0).unlink()                           # 删除最旧的文件


def create_csv(reg_map: dict):
    """
    创建新的 CSV 文件并写入表头
    :param reg_map: 变量映射字典
    :return: (文件对象, csv writer对象, 文件名)
    """
    filename = f"data_log_{datetime.now():%Y%m%d_%H%M%S}.csv"  # 生成带时间戳的文件名
    f = open(filename, 'w', newline='', encoding='utf-8-sig')   # 创建文件，使用 UTF-8 BOM 编码
    w = csv.writer(f)                                   # 创建 CSV 写入器
    w.writerow(build_headers(reg_map))                  # 写入表头行
    f.flush()                                           # 立即刷新到磁盘，确保表头已保存
    return f, w, filename                               # 返回文件对象、写入器和文件名
