"""
CSV 文件管理模块

功能概述：
  负责采集数据的持久化存储，将每次采集的结果以 CSV 文件形式保存到本地磁盘。
  支持自动文件轮转（达到行数上限后创建新文件）和旧文件清理（只保留最新 N 个文件）。

CSV 文件命名规则：
  data_log_20260520_143015.csv
  ↑        ↑        ↑
  前缀    日期      时间

文件编码：
  使用 UTF-8 BOM 编码（utf-8-sig），确保 Excel 打开中文不会乱码。
  BOM（Byte Order Mark）是文件开头的特殊标记，告诉 Excel 使用 UTF-8 解码。

文件轮转流程：
  1. 每写入一行数据，data_rows 计数器 +1
  2. 当 data_rows >= ROWS_PER_FILE 时，关闭当前文件
  3. 清理旧文件（只保留最新的 MAX_CSV_FILES 个）
  4. 创建新文件并写入表头
"""

import csv                                                     # Python 内置 CSV 读写模块
from datetime import datetime                                  # 时间模块，用于生成带时间戳的文件名
from pathlib import Path                                       # 路径模块，用于查找和删除旧文件


def build_headers(reg_map: dict) -> list:
    """
    根据变量映射表构建 CSV 表头行

    表头格式：时间戳, 变量名1(描述1), 变量名2(描述2), ...
    第一列固定为"时间戳"，后续列按变量地址从小到大排列。

    :param reg_map: 变量映射字典 {地址: (类型, 名称, 描述, 字节地址, 位号)}
    :return:        表头字符串列表，如 ["时间戳", "温度1(℃)", "压力(bar)"]
    """
    headers = ["时间戳"]                                       # 第一列固定为时间戳
    for addr in sorted(reg_map.keys()):                        # 按地址从小到大排序遍历
        _, name, desc, *_ = reg_map[addr]                      # 解包：只取类型、名称、描述
        if desc:                                               # 如果有描述信息
            headers.append(f"{name}({desc})")                  # 格式：变量名(描述)，如 "温度1(℃)"
        else:                                                  # 无描述信息
            headers.append(name)                               # 只用变量名
    return headers                                             # 返回完整的表头列表


def build_row(timestamp: str, values: dict, reg_map: dict, fmt_func) -> list:
    """
    构建一行 CSV 数据

    将当前时间戳和所有变量的值组装为一行数据。
    变量值通过 fmt_func 函数格式化为字符串，确保 CSV 中的数据格式统一。

    :param timestamp: 时间戳字符串，如 "2026-05-20 14:30:15.123"
    :param values:    解析后的值字典 {变量键: 实际值}，由 parse_registers() 返回
    :param reg_map:   变量映射字典
    :param fmt_func:  格式化函数，签名 (dtype, val) -> str，来自 display.py 的 fmt_value
    :return:          一行数据列表，如 ["2026-05-20 14:30:15.123", "100.0", "true", ...]
    """
    row = [timestamp]                                          # 第一列为时间戳
    for addr in sorted(reg_map.keys()):                        # 按地址排序，与表头顺序一致
        dtype = reg_map[addr][0]                               # 获取该变量的数据类型
        row.append(fmt_func(dtype, values.get(addr)))          # 格式化值并添加到行中
    return row                                                 # 返回完整的一行数据


def cleanup_old_files(max_keep: int):
    """
    清理旧的 CSV 日志文件，只保留最新的 max_keep 个

    工作流程：
      1. 查找当前目录下所有匹配 "data_log_*.csv" 模式的文件
      2. 按文件修改时间排序（旧的在前，新的在后）
      3. 如果文件数量超过上限，从最旧的开始逐个删除

    :param max_keep: 最多保留的文件数量，超过此数量的旧文件将被删除
    """
    # 查找所有 CSV 日志文件并按修改时间排序（升序，最旧的在前）
    files = sorted(
        Path(".").glob("data_log_*.csv"),                      # 使用通配符匹配所有日志文件
        key=lambda f: f.stat().st_mtime                        # 排序依据：文件的最后修改时间
    )
    while len(files) > max_keep:                               # 文件数量超过保留上限
        files.pop(0).unlink()                                  # 删除列表第一个元素（最旧的文件）


def create_csv(reg_map: dict):
    """
    创建新的 CSV 日志文件并写入表头

    文件名格式：data_log_YYYYMMDD_HHMMSS.csv（精确到秒，避免重名）
    文件编码：UTF-8 BOM（utf-8-sig），确保 Excel 打开中文不乱码

    :param reg_map: 变量映射字典，用于生成表头
    :return:        三元组 (文件对象, csv.writer 对象, 文件名)
                    - 文件对象：用于后续写入数据和关闭文件
                    - csv.writer：用于调用 writerow() 写入行数据
                    - 文件名：用于终端提示用户文件已保存
    """
    filename = f"data_log_{datetime.now():%Y%m%d_%H%M%S}.csv" # 用当前时间生成唯一文件名
    f = open(filename, 'w', newline='', encoding='utf-8-sig')  # 创建文件：写模式、无多余换行、UTF-8 BOM 编码
    w = csv.writer(f)                                          # 创建 CSV 写入器对象
    w.writerow(build_headers(reg_map))                         # 写入表头行（变量名列表）
    f.flush()                                                  # 立即刷新到磁盘，防止程序崩溃时表头丢失
    return f, w, filename                                      # 返回 (文件对象, 写入器, 文件名)
