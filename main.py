"""
Modbus TCP 数据采集程序
从 Modbus_Map.xlsx 读取变量表，持续采集 PLC 数据并输出
自动分文件保存 CSV，旧文件自动清理

依赖：pip install pymodbus openpyxl
用法：python main.py
"""

# ======================== 配置区（按需修改） ========================
PLC_IP = "192.168.0.99"          # PLC 的 IP 地址
PLC_PORT = 502                   # Modbus TCP 端口，默认 502
UNIT_ID = 1                      # 从站地址（Unit ID）
TIMEOUT = 3                      # 连接超时时间（秒）
SAMPLE_INTERVAL_MS = 1000        # 采集间隔（毫秒），1000 = 每秒采集一次
MAP_FILE = "Modbus_Map.xlsx"     # 变量表文件名，与程序同目录
ROWS_PER_FILE = 30               # 每个 CSV 文件保存的数据行数
MAX_CSV_FILES = 6                # 文件夹内最多保留的 CSV 文件数量
# ===================================================================

# 导入系统模块
import time                        # 用于延时等待
import signal                      # 用于捕获 Ctrl+C 信号
from datetime import datetime      # 用于获取当前时间

# 导入自定义模块
from modbus_client import ModbusClient           # Modbus TCP 客户端封装
from data_converter import convert_registers, DataType  # 数据类型转换
from excel_reader import load_register_map, calc_read_range  # Excel 变量表读取
from csv_manager import create_csv, build_row, cleanup_old_files  # CSV 文件管理
from display import fmt_value, print_table       # 终端表格显示


def parse_registers(all_regs: list, reg_start: int, reg_map: dict) -> dict:
    """
    将批量读取的原始寄存器值按配置解析为 {地址: 值}
    :param all_regs:  原始寄存器值列表，由 Modbus 返回
    :param reg_start: 批量读取的起始地址
    :param reg_map:   变量表，格式为 {地址: (数据类型, 变量名, 描述)}
    :return:          解析后的字典，格式为 {地址: 实际值}
    """
    result = {}                                         # 存储解析结果
    for addr, (dtype, _, _) in reg_map.items():         # 遍历变量表中每个变量
        idx = addr - reg_start                          # 计算在寄存器列表中的索引
        cnt = DataType.REGISTER_COUNT.get(dtype, 1)     # 获取该类型占用的寄存器数量
        try:
            data = all_regs[idx:idx + cnt]              # 截取对应的寄存器数据
            if len(data) >= cnt:                        # 数据长度足够才转换
                result[addr] = convert_registers(data, dtype)  # 转换为实际值
            else:
                result[addr] = None                     # 数据不足，标记为 None
        except (IndexError, ValueError):
            result[addr] = None                         # 异常时标记为 None
    return result                                       # 返回解析结果


def main():
    """主函数：读取变量表 → 连接 PLC → 循环采集 → 输出/保存"""

    # 1. 读取 Excel 变量表
    reg_map = load_register_map(MAP_FILE)               # 从 Excel 加载变量配置
    if not reg_map:                                     # 如果变量表为空
        print("变量表为空，请检查 Modbus_Map.xlsx")      # 提示用户检查文件
        return                                          # 退出程序

    # 2. 计算读取范围
    reg_start, reg_count = calc_read_range(reg_map)     # 计算批量读取的起始地址和数量

    # 3. 连接 PLC
    client = ModbusClient(PLC_IP, PLC_PORT, UNIT_ID, TIMEOUT)  # 创建客户端实例
    if not client.connect():                            # 尝试连接
        print(f"无法连接到 {PLC_IP}:{PLC_PORT}")         # 连接失败则提示
        return                                          # 退出程序

    # 4. 打印启动信息
    print(f"已连接到 {PLC_IP}:{PLC_PORT}")               # 显示连接成功
    print(f"变量表: {MAP_FILE}（{len(reg_map)} 个变量）") # 显示变量数量
    print(f"读取范围: 地址 {reg_start}~{reg_start + reg_count - 1}")  # 显示地址范围
    print(f"采集间隔: {SAMPLE_INTERVAL_MS}ms | 每 {ROWS_PER_FILE} 条换文件 | 保留 {MAX_CSV_FILES} 个")
    print(f"按 Ctrl+C 停止\n")                          # 提示停止方式

    # 5. 创建第一个 CSV 文件
    csv_file, csv_writer, csv_name = create_csv(reg_map)  # 创建 CSV 并写入表头
    data_rows = 0                                       # 当前文件已写入的数据行数
    display_lines = len(reg_map) + 3                    # 终端显示的总行数（用于清屏重绘）
    interval_s = SAMPLE_INTERVAL_MS / 1000.0            # 将毫秒转为秒
    running = True                                      # 程序运行标志

    # 6. 注册 Ctrl+C 信号处理
    def stop(sig, frame):
        nonlocal running                                # 引用外部变量
        running = False                                 # 收到信号后设置为 False
    signal.signal(signal.SIGINT, stop)                  # 注册信号处理函数

    # 7. 采集循环
    try:
        first = True                                    # 首次循环标志（不清屏）
        while running:                                  # 主循环，直到 Ctrl+C
            # 读取保持寄存器（FC 0x03）
            all_regs = client.read_holding_registers(reg_start, reg_count)

            # 获取当前时间戳
            now = f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3]  # 精确到毫秒

            if all_regs:                                # 读取成功
                # 解析寄存器数据
                values = parse_registers(all_regs, reg_start, reg_map)

                # 清屏重绘（非首次循环）
                if not first:
                    print(f"\033[{display_lines}A", end="")  # 光标上移 N 行
                first = False                           # 标记已非首次

                # 打印表格
                print(f"[{now}]")                       # 打印时间戳
                print_table(values, reg_map)            # 打印数据表格
                print()                                 # 空行分隔

                # 写入 CSV
                csv_writer.writerow(build_row(now, values, reg_map, fmt_value))
                csv_file.flush()                        # 立即刷新到磁盘
                data_rows += 1                          # 行数计数器加 1

                # 检查是否需要切换文件
                if data_rows >= ROWS_PER_FILE:          # 达到行数上限
                    csv_file.close()                    # 关闭当前文件
                    print(f"已保存: {csv_name}")         # 提示已保存
                    cleanup_old_files(MAX_CSV_FILES)    # 清理旧文件
                    csv_file, csv_writer, csv_name = create_csv(reg_map)  # 创建新文件
                    data_rows = 0                       # 重置行数计数器
            else:                                       # 读取失败
                print(f"[{now}] 读取失败")               # 打印错误信息

            time.sleep(interval_s)                      # 等待下一次采集

    finally:
        # 8. 清理退出
        csv_file.close()                                # 关闭 CSV 文件
        cleanup_old_files(MAX_CSV_FILES)                # 清理多余的旧文件
        client.disconnect()                             # 断开 PLC 连接
        print(f"\n已保存: {csv_name}")                   # 打印最后保存的文件名
        print("已断开连接")                              # 提示已断开


# 程序入口
if __name__ == "__main__":
    main()                                              # 运行主函数
