"""
数据类型转换模块
处理 PLC 寄存器值与实际数据类型之间的转换
西门子 PLC 使用大端字节序（Big-Endian），与 Modbus 标准一致
"""

import struct                                                 # 二进制数据打包/解包模块


# ======================== 数据类型定义 ========================
class DataType:
    """定义所有支持的数据类型及其占用的寄存器数量"""

    INT16 = "int16"                                           # 有符号16位整数，占1个寄存器
    UINT16 = "uint16"                                         # 无符号16位整数，占1个寄存器
    INT32 = "int32"                                           # 有符号32位整数，占2个寄存器
    UINT32 = "uint32"                                         # 无符号32位整数，占2个寄存器
    FLOAT32 = "float32"                                       # 32位浮点数，占2个寄存器
    BOOL16 = "bool16"                                         # 布尔值，占1个寄存器

    # 每种类型占用的寄存器数量映射表
    REGISTER_COUNT = {
        "int16": 1,                                           # int16 占 1 个寄存器（2字节）
        "uint16": 1,                                          # uint16 占 1 个寄存器（2字节）
        "int32": 2,                                           # int32 占 2 个寄存器（4字节）
        "uint32": 2,                                          # uint32 占 2 个寄存器（4字节）
        "float32": 2,                                         # float32 占 2 个寄存器（4字节）
        "bool16": 1,                                          # bool16 占 1 个寄存器
    }


# ======================== 寄存器 → 值 =========================
def register_to_int16(value: int) -> int:
    """
    无符号寄存器值 → 有符号16位整数

    :param value: 寄存器值（0~65535）
    :return: 有符号整数（-32768~32767）
    """
    if value >= 0x8000:                                       # 最高位为1，表示负数
        return value - 0x10000                                # 减去 65536 得到负数值
    return value                                              # 正数直接返回


def register_to_uint16(value: int) -> int:
    """
    寄存器值 → 无符号16位整数

    :param value: 寄存器值
    :return: 无符号整数（0~65535）
    """
    return value & 0xFFFF                                     # 与 0xFFFF 按位与，保留低16位


def registers_to_int32(registers: list) -> int:
    """
    2个寄存器 → 有符号32位整数（大端序，高字在前）

    :param registers: 包含2个寄存器值的列表
    :return: 有符号32位整数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个16位值打包为4字节
    return struct.unpack('>i', packed)[0]                     # 按有符号32位整数解包


def registers_to_uint32(registers: list) -> int:
    """
    2个寄存器 → 无符号32位整数（大端序，高字在前）

    :param registers: 包含2个寄存器值的列表
    :return: 无符号32位整数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个16位值打包为4字节
    return struct.unpack('>I', packed)[0]                     # 按无符号32位整数解包


def register_to_bool16(value: int) -> bool:
    """
    寄存器值 → 布尔值（256=true，0=false）

    :param value: 寄存器值
    :return: True 或 False
    """
    return value == 256                                       # 值等于256表示true


def registers_to_float(registers: list) -> float:
    """
    2个寄存器 → 32位浮点数（大端序，IEEE 754 标准）

    :param registers: 包含2个寄存器值的列表
    :return: 32位浮点数
    """
    packed = struct.pack('>HH', registers[0], registers[1])   # 将两个16位值打包为4字节
    return struct.unpack('>f', packed)[0]                     # 按 IEEE 754 浮点数解包


# ======================== 值 → 寄存器 =========================
def int16_to_register(value: int) -> int:
    """
    有符号16位整数 → 寄存器值（用于写入 PLC）

    :param value: 有符号整数（-32768~32767）
    :return: 寄存器值（0~65535）
    """
    if value < 0:                                             # 负数
        return value + 0x10000                                # 加 65536 转为无符号表示
    return value                                              # 正数直接返回


def int32_to_registers(value: int) -> list:
    """
    有符号32位整数 → 2个寄存器（大端序，用于写入 PLC）

    :param value: 有符号32位整数
    :return: 包含2个寄存器值的列表
    """
    packed = struct.pack('>i', value)                         # 按有符号32位整数打包为4字节
    return list(struct.unpack('>HH', packed))                 # 拆分为两个16位寄存器值


def uint32_to_registers(value: int) -> list:
    """
    无符号32位整数 → 2个寄存器（大端序，用于写入 PLC）

    :param value: 无符号32位整数
    :return: 包含2个寄存器值的列表
    """
    packed = struct.pack('>I', value)                         # 按无符号32位整数打包为4字节
    return list(struct.unpack('>HH', packed))                 # 拆分为两个16位寄存器值


def float_to_registers(value: float) -> list:
    """
    32位浮点数 → 2个寄存器（大端序，用于写入 PLC）

    :param value: 32位浮点数
    :return: 包含2个寄存器值的列表
    """
    packed = struct.pack('>f', value)                         # 按 IEEE 754 浮点数打包为4字节
    return list(struct.unpack('>HH', packed))                 # 拆分为两个16位寄存器值


# ======================== 统一转换接口 =========================
def convert_registers(registers: list, data_type: str):
    """
    根据数据类型将寄存器值列表转换为实际值

    :param registers: 原始寄存器值列表，由 Modbus 返回
    :param data_type: 数据类型字符串，如 "int16"、"float32"
    :return: 转换后的实际值（int/float/bool）
    """
    if data_type == DataType.INT16:                           # int16 类型
        return register_to_int16(registers[0])                # 取第一个寄存器转换
    elif data_type == DataType.UINT16:                        # uint16 类型
        return register_to_uint16(registers[0])               # 取第一个寄存器转换
    elif data_type == DataType.INT32:                         # int32 类型
        return registers_to_int32(registers)                  # 取两个寄存器转换
    elif data_type == DataType.UINT32:                        # uint32 类型
        return registers_to_uint32(registers)                 # 取两个寄存器转换
    elif data_type == DataType.FLOAT32:                       # float32 类型
        return registers_to_float(registers)                  # 取两个寄存器转换
    elif data_type == DataType.BOOL16:                        # bool16 类型
        return register_to_bool16(registers[0])               # 判断是否等于256
    else:                                                     # 未知类型
        return registers[0]                                   # 直接返回原始值
