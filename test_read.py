"""
快速测试脚本
读取 Modbus 寄存器并按 Excel 变量表解析
用于验证变量读取是否正确
"""

import sys                                                    # 系统模块
sys.path.insert(0, ".")                                       # 添加当前目录到路径

from modbus_client import ModbusClient                         # Modbus 客户端
from excel_reader import load_register_map, calc_read_range, parse_registers  # Excel 工具

# ======================== 测试配置 ========================
PLC_IP = "192.168.0.1"                                       # PLC IP 地址（根据实际修改）
PLC_PORT = 502                                               # Modbus TCP 端口
UNIT_ID = 1                                                  # 从站 ID
MAP_FILE = "Modbus_Map.xlsx"                                 # 变量表文件


def main():
    """主测试函数"""

    # ===== 1. 读取变量表 =====
    reg_map = load_register_map(MAP_FILE)                    # 加载变量映射表
    if not reg_map:                                          # 变量表为空
        print("变量表为空")                                  # 打印错误
        return                                               # 退出

    # 打印变量表内容
    print("=" * 70)                                          # 分隔线
    print("变量表内容（按地址排序）：")                       # 标题
    print("=" * 70)                                          # 分隔线
    for key in sorted(reg_map.keys()):                       # 遍历所有变量
        dtype, name, desc, byte_addr, bit_num = reg_map[key] # 解包变量信息
        if bit_num is not None:                              # 有位号
            offset_str = f"字节{byte_addr}.位{bit_num}"      # 格式化偏移
        else:                                                # 无位号
            offset_str = f"字节{byte_addr}"                  # 格式化偏移
        print(f"  [{offset_str:<12s}]  {dtype:<10s}  {name}")  # 打印变量信息

    # ===== 2. 计算读取范围 =====
    reg_start, reg_count = calc_read_range(reg_map)          # 计算读取范围
    print(f"\n读取范围: 地址 {reg_start}, 数量 {reg_count}")  # 打印范围

    # ===== 3. 连接 PLC =====
    client = ModbusClient(PLC_IP, PLC_PORT, UNIT_ID)         # 创建客户端
    if not client.connect():                                 # 连接失败
        print("无法连接到 PLC")                              # 打印错误
        return                                               # 退出

    # ===== 4. 读取原始寄存器 =====
    all_regs = client.read_holding_registers(                 # 读取寄存器
        reg_start, reg_count)                                # 起始地址和数量
    client.disconnect()                                      # 断开连接

    if not all_regs:                                         # 读取失败
        print("读取失败")                                    # 打印错误
        return                                               # 退出

    # 打印原始寄存器值
    print(f"\n{'=' * 70}")
    print(f"原始寄存器值（地址 {reg_start} 起，共 {reg_count} 个）：")
    print(f"{'=' * 70}")
    for i, val in enumerate(all_regs):                       # 遍历寄存器
        addr = reg_start + i                                 # 计算地址
        print(f"  Reg {addr} = {val:>5d}  = 0x{val:04X}  = {val:016b}")  # 打印值

    # ===== 5. 按变量表解析 =====
    values = parse_registers(all_regs, reg_start, reg_map)   # 解析寄存器值

    print(f"\n{'=' * 70}")
    print("解析结果：")
    print(f"{'=' * 70}")
    for key in sorted(reg_map.keys()):                       # 遍历所有变量
        dtype, name, desc, byte_addr, bit_num = reg_map[key] # 解包变量信息
        val = values.get(key)                                # 获取值
        if bit_num is not None:                              # 有位号
            offset_str = f"字节{byte_addr}.位{bit_num}"      # 格式化偏移
        else:                                                # 无位号
            offset_str = f"字节{byte_addr}"                  # 格式化偏移
        print(f"  {name:<30s}  {offset_str:<14s}  {val}")    # 打印解析结果

    # ===== 6. 逐寄存器显示位状态 =====
    print(f"\n{'=' * 70}")
    print("各寄存器位状态（方便对照 PLC）：")
    print(f"{'=' * 70}")
    for i, val in enumerate(all_regs):                       # 遍历寄存器
        addr = reg_start + i                                 # 计算地址
        bits = []                                            # 位列表
        for b in range(16):                                  # 遍历16位
            if val & (1 << b):                               # 位为1
                bits.append(str(b))                          # 添加到位列表
        bit_str = ", ".join(bits) if bits else "(全部为0)"    # 格式化位字符串
        print(f"  Reg {addr} (0x{val:04X}): 置位的位 = [{bit_str}]")  # 打印位状态


if __name__ == "__main__":                                   # 直接运行时
    main()                                                   # 调用主函数
