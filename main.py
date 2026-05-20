"""
Modbus TCP 数据采集程序 — 主程序

功能概述：
  从 TIA Portal 导出的 Modbus_Map.xlsx 变量表中读取 PLC 变量配置，
  通过 Modbus TCP 协议持续采集西门子 PLC 的寄存器数据，
  将采集结果实时显示在终端，并以 CSV 文件形式记录到本地磁盘。

程序流程：
  1. 读取配置参数（本文件顶部）
  2. 初始化采集器，加载 Excel 变量表
  3. 建立与 PLC 的 Modbus TCP 连接
  4. 进入采集循环：读取寄存器 → 解析为实际值 → 终端显示 → CSV 写入
  5. 支持断线自动重连和 Ctrl+C 优雅退出

文件结构：
  main.py              → 本文件，程序入口 + 所有可配置参数
  modbus_client.py     → Modbus TCP 通讯客户端（封装 pymodbus）
  data_acquisition.py  → 数据采集器（封装连接、读取、重连逻辑）
  data_converter.py    → 数据类型转换（寄存器值 ↔ 实际值）
  excel_reader.py      → Excel 变量表读取（解析 TIA Portal 导出格式）
  csv_manager.py       → CSV 文件管理（创建、写入、轮转、清理）
  display.py           → 终端表格显示

依赖安装：pip install pymodbus openpyxl
启动方式：python main.py
"""

# ======================== 所有可配置参数（修改此处即可调整程序行为） ========================

# --- PLC 通讯参数 ---
PLC_IP = "192.168.0.99"                  # PLC 的 IP 地址，需与实际 PLC 一致
PLC_PORT = 502                           # Modbus TCP 端口号，西门子 PLC 默认 502
UNIT_ID = 1                              # Modbus 从站 ID（Unit ID），西门子 PLC 默认 1
TIMEOUT = 3                              # TCP 连接超时时间（单位：秒），超时则认为通讯失败
RECONNECT_DELAY = 2                      # 连接断开后，等待多久再尝试重连（单位：秒）
RETRY_DELAY = 3                          # 重连失败后，等待多久再进行下一次重试（单位：秒）

# --- 采集控制参数 ---
MAP_FILE = "Modbus_Map.xlsx"             # Modbus 变量表文件路径（TIA Portal 导出的 Excel）
SAMPLE_INTERVAL_MS = 1000                # 采集间隔（单位：毫秒），1000 = 每秒采集一次

# --- CSV 存储参数 ---
ROWS_PER_FILE = 30                       # 每个 CSV 文件最多写入多少行数据后自动切换新文件
MAX_CSV_FILES = 6                        # 最多同时保留多少个 CSV 旧文件，超出后自动删除最旧的

# --- 终端显示参数 ---
DISPLAY_LINES_OFFSET = 3                 # 终端显示占用的额外行数（表头1行 + 分隔线1行 + 空行1行）
                                         # 用于光标上移覆盖旧数据，实现终端原地刷新效果

# ========================================================================================


import time                                                   # 时间模块，用于采集间隔延时和重连等待
import signal                                                 # 信号模块，用于捕获 Ctrl+C 实现优雅退出

from data_acquisition import DataAcquisition                  # 数据采集器，封装了连接、读取、重连等全部逻辑
from csv_manager import create_csv, build_row, cleanup_old_files  # CSV 工具：创建文件、构建数据行、清理旧文件
from display import fmt_value, print_table                    # 终端显示工具：格式化单个值、打印变量表格


def main():
    """
    程序主入口函数

    执行流程：
      1. 创建采集器实例，传入通讯参数
      2. 加载 Excel 变量表，获取变量映射关系
      3. 连接 PLC
      4. 创建首个 CSV 日志文件
      5. 进入主循环：读取 → 解析 → 显示 → 写入 CSV
      6. 支持断线重连和 Ctrl+C 退出时的资源清理
    """

    # ========== 第1步：初始化采集器 ==========
    # 将所有通讯参数传入采集器，采集器内部会创建 Modbus 客户端
    collector = DataAcquisition(
        plc_ip=PLC_IP,                                         # PLC 的 IP 地址
        plc_port=PLC_PORT,                                     # Modbus TCP 端口号
        unit_id=UNIT_ID,                                       # 从站 ID
        timeout=TIMEOUT,                                       # 超时秒数
        reconnect_delay=RECONNECT_DELAY,                       # 重连等待秒数
        retry_delay=RETRY_DELAY                                # 重试等待秒数
    )

    # ========== 第2步：加载 Excel 变量表 ==========
    # 变量表定义了 PLC 中每个变量的名称、数据类型、字节地址等信息
    # 加载后，采集器会自动计算出需要读取的 Modbus 地址范围
    if not collector.load_map(MAP_FILE):                       # 加载失败（文件不存在或变量表为空）
        print("变量表为空，请检查 Modbus_Map.xlsx")            # 提示用户检查文件
        return                                                 # 退出程序

    # ========== 第3步：连接 PLC ==========
    # 通过 Modbus TCP 协议建立与 PLC 的网络连接
    if not collector.connect():                                # 连接失败（PLC 不在线或网络不通）
        print(f"无法连接到 {PLC_IP}:{PLC_PORT}")               # 提示用户检查网络和 PLC 状态
        return                                                 # 退出程序

    # ========== 第4步：打印连接信息 ==========
    # 从采集器中获取变量映射表和读取范围，用于显示
    reg_map = collector.reg_map                                # 变量映射表 {地址: (类型, 名称, 描述, 字节地址, 位号)}
    reg_start = collector.reg_start                            # 批量读取的起始 Modbus 地址
    reg_count = collector.reg_count                            # 需要读取的寄存器总数
    print(f"已连接到 {PLC_IP}:{PLC_PORT}")                     # 打印 PLC 连接地址
    print(f"变量表: {MAP_FILE}（{len(reg_map)} 个变量）")       # 打印变量表文件名和变量数量
    print(f"读取范围: 地址 {reg_start}~{reg_start + reg_count - 1}")  # 打印 Modbus 地址范围
    print(f"采集间隔: {SAMPLE_INTERVAL_MS}ms | 每 {ROWS_PER_FILE} 条换文件 | 保留 {MAX_CSV_FILES} 个")  # 打印运行参数
    print(f"按 Ctrl+C 停止\n")                                 # 提示退出方式

    # ========== 第5步：创建首个 CSV 日志文件 ==========
    # CSV 文件用于持久化存储采集数据，方便后续用 Excel 打开分析
    csv_file, csv_writer, csv_name = create_csv(reg_map)       # 创建文件，写入表头，返回文件对象和写入器
    data_rows = 0                                              # 当前 CSV 文件已写入的数据行数，用于判断是否需要轮转
    display_lines = len(reg_map) + DISPLAY_LINES_OFFSET        # 终端显示占用的总行数，用于光标上移覆盖
    running = True                                             # 主循环运行标志，Ctrl+C 时置为 False 退出循环

    # ========== 第6步：注册 Ctrl+C 信号处理 ==========
    def stop(sig, frame):
        """
        Ctrl+C 信号处理函数
        当用户按下 Ctrl+C 时，Python 会调用此函数
        仅将 running 标志置为 False，让主循环在下一次迭代时自然退出
        这样可以确保 finally 块中的资源清理代码（关闭文件、断开连接）能够正常执行
        """
        nonlocal running                                       # 声明使用外层函数的 running 变量
        running = False                                        # 置为 False，主循环将在下次判断时退出

    signal.signal(signal.SIGINT, stop)                         # 将 Ctrl+C（SIGINT 信号）绑定到 stop 函数

    # ========== 第7步：主采集循环 ==========
    try:
        first = True                                           # 首次采集标志，首次不执行光标上移（因为还没有旧数据可覆盖）
        while running:                                         # 主循环，Ctrl+C 后 running 变为 False 时退出

            # --- 7.1 读取寄存器 ---
            all_regs = collector.read_registers()              # 批量读取所有保持寄存器，返回原始值列表

            # --- 7.2 处理连接断开 ---
            # 如果读取返回空列表，且客户端对象仍存在，说明连接已断开（不是首次未连接）
            if not all_regs and collector.client:
                print("\n连接断开，正在重连...")                # 提示用户正在重连
                if collector.reconnect():                      # 尝试断线重连（断开旧连接 → 等待 → 建立新连接）
                    print(f"重连成功: {PLC_IP}:{PLC_PORT}")    # 重连成功
                    first = True                               # 重置首次标志，下一次采集重新开始覆盖显示
                else:                                          # 重连失败（PLC 可能已关机或网络中断）
                    print(f"重连失败，{RETRY_DELAY}秒后重试...")  # 提示等待后重试
                    time.sleep(RETRY_DELAY)                    # 等待指定时间后，循环会再次尝试读取和重连
                continue                                       # 跳过本次循环的后续步骤（显示、CSV写入等），直接进入下一次

            # --- 7.3 获取当前时间戳 ---
            now = collector.get_timestamp()                    # 格式：2026-05-20 14:30:15.123（精确到毫秒）

            # --- 7.4 读取成功：解析 → 显示 → 写入 CSV ---
            if all_regs:                                       # 寄存器读取成功，all_regs 非空
                values = collector.parse_values(all_regs)      # 将原始寄存器值解析为 {变量键: 实际值} 字典

                # 终端原地刷新显示（覆盖上一次的输出）
                if not first:                                  # 非首次采集，需要光标上移覆盖旧数据
                    print(f"\033[{display_lines}A", end="")   # ANSI 转义码：光标上移 display_lines 行
                first = False                                  # 首次采集已完成，后续都需要覆盖
                print(f"[{now}]")                              # 打印当前时间戳
                print_table(values, reg_map)                   # 以表格形式打印所有变量的当前值
                print()                                        # 打印空行，与下次覆盖保持对齐

                # 写入 CSV 文件
                csv_writer.writerow(                           # 写入一行数据到 CSV
                    build_row(now, values, reg_map, fmt_value) # 构建数据行：[时间戳, 值1, 值2, ...]
                )
                csv_file.flush()                               # 立即刷新写入磁盘，防止程序异常退出时丢失数据
                data_rows += 1                                 # 当前行数 +1

                # CSV 文件轮转：达到行数上限后切换新文件
                if data_rows >= ROWS_PER_FILE:                 # 当前文件已写满
                    csv_file.close()                           # 关闭当前文件
                    print(f"已保存: {csv_name}")               # 提示用户文件已保存
                    cleanup_old_files(MAX_CSV_FILES)           # 清理旧文件，只保留最新的 MAX_CSV_FILES 个
                    csv_file, csv_writer, csv_name = create_csv(reg_map)  # 创建新的 CSV 文件
                    data_rows = 0                              # 重置行数计数器

            # --- 7.5 读取失败 ---
            else:                                              # 寄存器读取返回空列表（读取失败）
                print(f"[{now}] 读取失败")                     # 打印失败信息和时间戳

            # --- 7.6 等待下一次采集 ---
            time.sleep(SAMPLE_INTERVAL_MS / 1000.0)           # 将毫秒转为秒后等待

    # ========== 第8步：资源清理（无论正常退出还是异常都会执行） ==========
    finally:
        csv_file.close()                                       # 关闭当前 CSV 文件，确保数据完整写入磁盘
        cleanup_old_files(MAX_CSV_FILES)                       # 最终清理一次旧文件
        collector.disconnect()                                 # 断开与 PLC 的 Modbus TCP 连接，释放网络资源
        print(f"\n已保存: {csv_name}")                         # 提示最后保存的文件名
        print("已断开连接")                                    # 提示连接已断开


# 当直接运行此文件时（而非被其他文件 import 时），执行 main 函数
if __name__ == "__main__":
    main()
