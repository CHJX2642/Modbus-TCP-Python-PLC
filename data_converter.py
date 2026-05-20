"""
数据类型转换模块

功能概述：
  处理 Modbus 寄存器值（16位无符号整数）与 PLC 实际数据类型之间的相互转换。
  Modbus 协议中每个寄存器为 16 位（0~65535），而 PLC 中的数据类型多样：
    - 16位整数（int16/uint16）→ 占 1 个寄存器
    - 32位整数（int32/uint32）→ 占 2 个寄存器（高字在前，低字在后）
    - 32位浮点数（float32）   → 占 2 个寄存器（IEEE 754 标准）
    - 布尔值（bool16）        → 占 1 个寄存器（0=false，256=true）

字节序说明：
  西门子 PLC 使用大端字节序（Big-Endian），与 Modbus 标准一致。
  大端序 = 高位字节在前（低地址），低位字节在后（高地址）。
  例如：int32 值 0x12345678 存储为 [0x1234, 0x5678]（两个寄存器）

本模块包含三部分：
  1. DataType 类 — 定义数据类型常量和寄存器数量映射表
  2. 寄存器→值 转换函数 — 用于读取 PLC 数据后解析
  3. 值→寄存器 转换函数 — 用于写入 PLC 数据前编码
  4. convert_registers() — 统一转换接口，根据类型自动选择对应函数
"""

import struct                                                 # Python 内置模块，用于二进制数据的打包（pack）和解包（unpack）
                                                             # struct.pack()   → 将 Python 值转为字节串
                                                             # struct.unpack() → 将字节串转为 Python 值


# ======================== 数据类型定义 ========================
class DataType:
    """
    数据类型常量类

    定义了本程序支持的所有 PLC 数据类型，以及每种类型占用的寄存器数量。
    这些常量用于 excel_reader.py 的类型映射和 data_converter.py 的类型判断。

    寄存器数量决定了批量读取时需要多读几个寄存器：
      - 1 个寄存器的类型：读取 1 个值即可
      - 2 个寄存器的类型：需要连续读取 2 个值，然后拼接为 32 位数据
    """

    # 各类型占用的寄存器数量映射表
    # key = 类型名称字符串，value = 占用寄存器数量
    REGISTER_COUNT = {
        "int16": 1,                                           # 有符号16位整数，范围 -32768~32767，占 1 个寄存器（2字节）
        "uint16": 1,                                          # 无符号16位整数，范围 0~65535，占 1 个寄存器（2字节）
        "int32": 2,                                           # 有符号32位整数，范围 ±21亿，占 2 个寄存器（4字节）
        "uint32": 2,                                          # 无符号32位整数，范围 0~42亿，占 2 个寄存器（4字节）
        "float32": 2,                                         # 32位浮点数（IEEE 754），占 2 个寄存器（4字节）
        "bool16": 1,                                          # 布尔值，占 1 个寄存器（0=false，256=true）
    }


# ======================== 寄存器 → 值（用于读取 PLC 数据后解析） =========================

def register_to_int16(value: int) -> int:
    """
    将无符号寄存器值转换为有符号 16 位整数

    原理：
      寄存器是 16 位无符号的（0~65535），但 PLC 中的 int16 是有符号的（-32768~32767）。
      当最高位（bit15）为 1 时，表示负数，需要用补码转换：
        负数 = 寄存器值 - 65536（即减去 2^16）
      例如：寄存器值 65535 → 65535 - 65536 = -1

    :param value: 寄存器值（0~65535 的无符号整数）
    :return:      有符号整数（-32768~32767）
    """
    if value >= 0x8000:                                       # 最高位（bit15）为 1，说明是负数
        return value - 0x10000                                # 减去 65536 得到有符号值
    return value                                              # 最高位为 0，正数直接返回原值


def register_to_uint16(value: int) -> int:
    """
    将寄存器值转换为无符号 16 位整数

    原理：
      寄存器本身就是 16 位无符号的，直接取低 16 位即可。
      通过按位与 0xFFFF（二进制 16 个1）确保结果在 0~65535 范围内。

    :param value: 寄存器值
    :return:      无符号整数（0~65535）
    """
    return value & 0xFFFF                                     # 按位与 0xFFFF，保留低 16 位，屏蔽高位


def registers_to_int32(registers: list) -> int:
    """
    将 2 个寄存器值转换为有符号 32 位整数

    原理：
      32 位整数占 4 字节，由 2 个 16 位寄存器组成。
      大端序（Big-Endian）：高字在前（第一个寄存器），低字在后（第二个寄存器）。
      通过 struct 模块将 2 个 16 位值打包为 4 字节，再按有符号 32 位整数解包。

    :param registers: 包含 2 个寄存器值的列表，如 [0x0000, 0x000A] 表示 10
    :return:          有符号 32 位整数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个 16 位值打包为 4 字节（大端序）
                                                             # '>HH' 表示：大端序 + 两个 unsigned short
    return struct.unpack('>i', packed)[0]                     # 按有符号 32 位整数（'>i'）解包，取第一个结果


def registers_to_uint32(registers: list) -> int:
    """
    将 2 个寄存器值转换为无符号 32 位整数

    原理：与 registers_to_int32 类似，但按无符号整数解包。
    区别：int32 的范围是 ±21亿，uint32 的范围是 0~42亿。

    :param registers: 包含 2 个寄存器值的列表
    :return:          无符号 32 位整数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个 16 位值打包为 4 字节
    return struct.unpack('>I', packed)[0]                     # 按无符号 32 位整数（'>I'）解包


def register_to_bool16(value: int) -> bool:
    """
    将寄存器值转换为布尔值

    原理：
      西门子 PLC 中 Bool 类型存储在寄存器中时，使用特殊编码：
        - true（得电）= 256（即 0x0100，bit8 置位）
        - false（失电）= 0
      这是因为西门子 PLC 的 Bool 变量映射到寄存器的第 8 位（高字节的第 0 位）。

    :param value: 寄存器值
    :return:      True（值等于 256）或 False（值不等于 256）
    """
    return value == 256                                       # 只有值恰好等于 256 时才返回 True


def registers_to_float(registers: list) -> float:
    """
    将 2 个寄存器值转换为 32 位浮点数

    原理：
      32 位浮点数遵循 IEEE 754 标准，占 4 字节。
      由 2 个 16 位寄存器组成，大端序排列。
      通过 struct 模块将 2 个 16 位值打包为 4 字节，再按 IEEE 754 浮点数解包。

    :param registers: 包含 2 个寄存器值的列表，如 [0x4120, 0x0000] 表示 10.0
    :return:          32 位浮点数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个 16 位值打包为 4 字节
    return struct.unpack('>f', packed)[0]                     # 按 IEEE 754 浮点数（'>f'）解包


# ======================== 值 → 寄存器（用于写入 PLC 数据前编码） =========================

def int16_to_register(value: int) -> int:
    """
    将有符号 16 位整数转换为寄存器值（用于写入 PLC）

    原理：与 register_to_int16 相反。
      正数直接返回，负数需要加 65536 转为无符号表示。
      例如：-1 → -1 + 65536 = 65535

    :param value: 有符号整数（-32768~32767）
    :return:      寄存器值（0~65535）
    """
    if value < 0:                                             # 负数需要转换
        return value + 0x10000                                # 加上 65536 得到无符号表示
    return value                                              # 正数直接返回


def int32_to_registers(value: int) -> list:
    """
    将有符号 32 位整数转换为 2 个寄存器值（用于写入 PLC）

    原理：与 registers_to_int32 相反。
      将 32 位整数打包为 4 字节，再拆分为 2 个 16 位寄存器值。

    :param value: 有符号 32 位整数
    :return:      包含 2 个寄存器值的列表，如 10 → [0, 10]
    """
    packed = struct.pack('>i', value)                         # 按有符号 32 位整数打包为 4 字节
    return list(struct.unpack('>HH', packed))                 # 拆分为 2 个 16 位无符号整数


def uint32_to_registers(value: int) -> list:
    """
    将无符号 32 位整数转换为 2 个寄存器值（用于写入 PLC）

    原理：与 registers_to_uint32 相反。

    :param value: 无符号 32 位整数
    :return:      包含 2 个寄存器值的列表
    """
    packed = struct.pack('>I', value)                         # 按无符号 32 位整数打包为 4 字节
    return list(struct.unpack('>HH', packed))                 # 拆分为 2 个 16 位值


def float_to_registers(value: float) -> list:
    """
    将 32 位浮点数转换为 2 个寄存器值（用于写入 PLC）

    原理：与 registers_to_float 相反。
      将浮点数按 IEEE 754 标准打包为 4 字节，再拆分为 2 个寄存器值。

    :param value: 32 位浮点数，如 10.0
    :return:      包含 2 个寄存器值的列表，如 [0x4120, 0x0000]
    """
    packed = struct.pack('>f', value)                         # 按 IEEE 754 浮点数打包为 4 字节
    return list(struct.unpack('>HH', packed))                 # 拆分为 2 个 16 位值


# ======================== 统一转换接口 =========================

def convert_registers(registers: list, data_type: str):
    """
    统一转换接口：根据数据类型，自动选择对应的转换函数

    这是外部调用的入口函数，根据 data_type 参数自动分发到具体的转换函数。
    调用方无需关心底层的转换细节，只需传入寄存器值列表和类型名称即可。

    :param registers: 原始寄存器值列表（由 Modbus 读取返回）
                      - 16 位类型：列表中有 1 个元素
                      - 32 位类型：列表中有 2 个元素（高字在前）
    :param data_type: 数据类型字符串，必须是以下之一：
                      "int16"、"uint16"、"int32"、"uint32"、"float32"、"bool16"
    :return:          转换后的实际值（int / float / bool），未知类型返回原始寄存器值
    """
    if data_type == "int16":                                  # 有符号 16 位整数
        return register_to_int16(registers[0])                # 取第 1 个寄存器转换
    elif data_type == "uint16":                               # 无符号 16 位整数
        return register_to_uint16(registers[0])               # 取第 1 个寄存器转换
    elif data_type == "int32":                                # 有符号 32 位整数
        return registers_to_int32(registers)                  # 取前 2 个寄存器转换
    elif data_type == "uint32":                               # 无符号 32 位整数
        return registers_to_uint32(registers)                 # 取前 2 个寄存器转换
    elif data_type == "float32":                              # 32 位浮点数
        return registers_to_float(registers)                  # 取前 2 个寄存器转换
    elif data_type == "bool16":                               # 布尔值
        return register_to_bool16(registers[0])               # 取第 1 个寄存器转换
    else:                                                     # 未知的数据类型
        return registers[0]                                   # 直接返回原始值，不做转换
