"""
Modbus TCP 数据采集程序
从 Modbus_Map.xlsx 读取变量表，持续采集 PLC 数据
通过终端显示和 CSV 文件记录

架构：
- 配置层：本文件（所有可配置参数）
- 通讯层：modbus_client.py, data_converter.py, excel_reader.py
- 采集层：data_acquisition.py（封装采集逻辑）
- 展示层：shared_state.py, flask_app.py, display.py, csv_manager.py

依赖：pip install pymodbus openpyxl flask
用法：python main.py
"""

# ======================== PLC 通讯配置 ========================
PLC_IP = "192.168.0.99"                                       # PLC IP 地址（根据实际修改）
PLC_PORT = 502                                               # Modbus TCP 端口（默认 502）
UNIT_ID = 1                                                  # Modbus 从站 ID（默认 1）
TIMEOUT = 3                                                  # 通讯超时（秒）
RECONNECT_DELAY = 2                                          # 断线重连等待（秒）
RETRY_DELAY = 3                                              # 重连失败后重试等待（秒）

# ======================== 采集控制配置 ========================
MAP_FILE = "Modbus_Map.xlsx"                                 # Modbus 变量表文件路径
SAMPLE_INTERVAL_MS = 1000                                    # 采集间隔（毫秒）

# ======================== CSV 存储配置 ========================
ROWS_PER_FILE = 30                                           # 每个 CSV 文件最大行数
MAX_CSV_FILES = 6                                            # 最多保留的 CSV 文件数

# ======================== Web 服务配置 ========================
WEB_HOST = "0.0.0.0"                                         # Flask 绑定地址
WEB_PORT = 5000                                              # Flask 端口

# ======================== 终端显示配置 ========================
DISPLAY_LINES_OFFSET = 3                                     # 终端显示额外行数（表头+分隔线+空行）

# ============================================================

import time                                                   # 时间模块，用于延时
import signal                                                 # 信号模块，用于 Ctrl+C 退出
import threading                                              # 线程模块，用于启动 Flask

from data_acquisition import DataAcquisition                  # 导入数据采集器
from csv_manager import create_csv, build_row, cleanup_old_files  # 导入 CSV 管理工具
from display import fmt_value, print_table                    # 导入终端显示工具
from shared_state import state                                # 导入共享状态单例


def run_flask():
    """在独立线程中运行 Flask Web 服务"""
    from flask_app import app                                  # 延迟导入避免循环引用
    app.run(host=WEB_HOST, port=WEB_PORT,                      # 启动服务
            debug=False, use_reloader=False,                   # 关闭调试和自动重载
            threaded=True)                                     # 开启多线程


def main():
    """程序入口：初始化 → 连接 → 采集循环"""

    # ===== 1. 初始化采集器 =====
    collector = DataAcquisition(                               # 创建数据采集器实例
        plc_ip=PLC_IP,                                         # PLC IP 地址
        plc_port=PLC_PORT,                                     # Modbus 端口
        unit_id=UNIT_ID,                                       # 从站 ID
        timeout=TIMEOUT,                                       # 超时时间
        reconnect_delay=RECONNECT_DELAY,                       # 重连延迟
        retry_delay=RETRY_DELAY                                # 重试延迟
    )

    # ===== 2. 加载变量表 =====
    if not collector.load_map(MAP_FILE):                       # 加载 Excel 变量表
        print("变量表为空，请检查 Modbus_Map.xlsx")            # 打印错误信息
        return                                                 # 退出程序

    # ===== 3. 启动 Web 服务 =====
    state.update_system(plc_connected=False)                   # 初始化系统状态
    flask_thread = threading.Thread(                           # 创建 Flask 线程
        target=run_flask, daemon=True)                         # 设为守护线程
    flask_thread.start()                                       # 启动 Flask
    print(f"Web 服务已启动: http://localhost:{WEB_PORT}")      # 打印启动信息

    # ===== 4. 连接 PLC =====
    if not collector.connect():                                # 连接 PLC
        print(f"无法连接到 {PLC_IP}:{PLC_PORT}")               # 打印错误信息
        return                                                 # 退出程序

    state.update_system(plc_connected=True)                    # 更新状态为已连接
    reg_map = collector.reg_map                                # 获取变量映射表
    reg_start = collector.reg_start                            # 获取起始地址
    reg_count = collector.reg_count                            # 获取寄存器数量

    # 打印连接信息
    print(f"已连接到 {PLC_IP}:{PLC_PORT}")
    print(f"变量表: {MAP_FILE}（{len(reg_map)} 个变量）")
    print(f"读取范围: 地址 {reg_start}~{reg_start + reg_count - 1}")
    print(f"采集间隔: {SAMPLE_INTERVAL_MS}ms | 每 {ROWS_PER_FILE} 条换文件 | 保留 {MAX_CSV_FILES} 个")
    print(f"按 Ctrl+C 停止\n")

    # ===== 5. 创建 CSV 文件 =====
    csv_file, csv_writer, csv_name = create_csv(reg_map)       # 创建首个 CSV 文件
    data_rows = 0                                              # 当前文件已写入行数
    display_lines = len(reg_map) + DISPLAY_LINES_OFFSET        # 终端显示占用行数
    interval_s = SAMPLE_INTERVAL_MS / 1000.0                   # 采集间隔转为秒
    running = True                                             # 运行标志

    def stop(sig, frame):
        """Ctrl+C 信号处理函数"""
        nonlocal running                                       # 修改外部变量
        running = False                                        # 停止循环

    signal.signal(signal.SIGINT, stop)                         # 注册信号处理

    # ===== 6. 采集循环 =====
    try:
        first = True                                           # 首次采集标志
        while running:                                         # 主循环
            all_regs = collector.read_registers()              # 读取寄存器

            # 处理连接断开
            if not all_regs and collector.client:
                state.update_system(plc_connected=False)       # 更新状态
                print(f"\n连接断开，正在重连...")               # 打印重连信息
                if collector.reconnect():                      # 尝试重连
                    print(f"重连成功: {PLC_IP}:{PLC_PORT}")
                    state.update_system(plc_connected=True)
                    first = True                               # 重置首次标志
                else:                                          # 重连失败
                    print(f"重连失败，{RETRY_DELAY}秒后重试...")
                    time.sleep(RETRY_DELAY)
                continue                                       # 跳过本次循环

            now = collector.get_timestamp()                    # 获取时间戳

            if all_regs:                                       # 读取成功
                values = collector.parse_values(all_regs)      # 解析寄存器值

                # 终端显示
                if not first:                                  # 非首次采集
                    print(f"\033[{display_lines}A", end="")    # 光标上移
                first = False
                print(f"[{now}]")                              # 打印时间戳
                print_table(values, reg_map)                   # 打印变量表格
                print()

                # CSV 写入
                csv_writer.writerow(
                    build_row(now, values, reg_map, fmt_value))
                csv_file.flush()
                data_rows += 1

                # 文件轮转
                if data_rows >= ROWS_PER_FILE:
                    csv_file.close()
                    print(f"已保存: {csv_name}")
                    cleanup_old_files(MAX_CSV_FILES)
                    csv_file, csv_writer, csv_name = create_csv(reg_map)
                    data_rows = 0

                # 更新共享状态
                state.update_values(values)
                state.update_system(plc_connected=True)

            else:                                              # 读取失败
                print(f"[{now}] 读取失败")
                state.update_system(plc_connected=False)

            time.sleep(interval_s)                             # 等待下次采集

    finally:                                                   # 清理资源
        csv_file.close()                                       # 关闭 CSV 文件
        cleanup_old_files(MAX_CSV_FILES)                       # 清理旧文件
        collector.disconnect()                                 # 断开连接
        state.update_system(plc_connected=False)               # 更新状态
        print(f"\n已保存: {csv_name}")
        print("已断开连接")


if __name__ == "__main__":
    main()
