"""
Excel 变量表读取模块

功能概述：
  从 TIA Portal 导出的 Modbus_Map.xlsx 文件中读取 PLC 变量配置，
  将 Excel 中的变量名、数据类型、字节地址等信息解析为程序可用的映射表。

TIA Portal 导出格式说明：
  Excel 文件的每一行代表一个 PLC 变量，包含以下关键列：
    A 列 — 变量名称（如 "温度1"、"电机运行"）
    B 列 — 数据类型（如 "Int"、"Real"、"Bool"、"DInt"）
    C 列 — 字节偏移地址（整数表示普通变量，小数表示位变量）

位寻址说明：
  TIA Portal 中 Bool 变量的字节偏移使用小数表示位号：
    0.0 = 字节 0 的第 0 位
    0.1 = 字节 0 的第 1 位
    3.7 = 字节 3 的第 7 位
  整数偏移（如 40）表示普通数值变量，从该字节地址开始读取。

Modbus 寄存器与字节的映射关系（标准大端序）：
  每个 Modbus 寄存器 = 2 个字节 = 16 位
  Reg N = 字节(2N) 的高字节 + 字节(2N+1) 的低字节
  例如：
    Reg 0 = 字节0(高) + 字节1(低)
    Reg 1 = 字节2(高) + 字节3(低)
  所以：字节偏移 ÷ 2 = Modbus 寄存器地址

映射表数据结构：
  返回的 reg_map 字典格式为：
    {地址: (数据类型, 变量名, 描述, 字节地址, 位号)}

  普通变量示例：
    {0: ("int16", "温度1", "", 0, None)}      → Reg 0，int16 类型
    {1: ("float32", "压力", "", 2, None)}     → Reg 1，float32 类型（占 Reg 1~2）

  位变量示例：
    {1.09: ("bit_9", "电机运行", "", 3, 1)}   → Reg 1 的第 9 位，Bool 类型
"""

from pathlib import Path                                      # 路径处理模块，用于检查文件是否存在
import openpyxl                                               # Excel 读写库，用于读取 .xlsx 文件
from data_converter import DataType, convert_registers        # 数据类型定义和寄存器转换函数


# TIA Portal 数据类型名称 → 程序内部类型名称的映射表
# TIA Portal 中的类型名称不区分大小写，且可能有多种写法
TYPE_MAP = {
    "int": "int16",      # TIA Portal 的 "Int" → 16位有符号整数（-32768~32767）
    "word": "uint16",    # TIA Portal 的 "Word" → 16位无符号整数（0~65535）
    "dint": "int32",     # TIA Portal 的 "DInt" → 32位有符号整数（±21亿）
    "dword": "uint32",   # TIA Portal 的 "DWord" → 32位无符号整数（0~42亿）
    "real": "float32",   # TIA Portal 的 "Real" → 32位浮点数（IEEE 754）
    "bool": "bool16",    # TIA Portal 的 "Bool" → 布尔值（true/false）
}


def _parse_byte_offset(raw):
    """
    解析 TIA Portal 的字节偏移值

    TIA Portal 导出的字节偏移有两种格式：
      - 整数（如 40）→ 表示普通数值变量，从字节 40 开始
      - 小数（如 0.1）→ 表示位变量，字节 0 的第 1 位

    解析规则：
      整数部分 = 字节地址
      小数部分 × 10 = 位号（0~7）

    :param raw: Excel 中的原始偏移值（整数或浮点数）
    :return:    (字节地址, 位号) 元组
                - 普通变量：(40, None)  → 字节地址 40，无位号
                - 位变量：  (0, 1)      → 字节地址 0，位号 1
    """
    val = float(raw)                                          # 先转为浮点数，统一处理整数和小数
    byte_addr = int(val)                                      # 整数部分 = 字节地址
    frac = val - byte_addr                                    # 计算小数部分
    if frac > 0.001:                                          # 小数部分 > 0，说明是位变量
        return byte_addr, round(frac * 10)                    # 小数 × 10 = 位号（四舍五入）
    return byte_addr, None                                    # 无小数部分，普通变量，位号为 None


def _byte_to_reg_bit(byte_addr, bit_num):
    """
    将 (字节地址, 位号) 转换为 (Modbus 寄存器地址, 寄存器内位号)

    西门子 PLC 的字节序与 Modbus 寄存器的映射关系：
      - 低字节地址（偶数）→ 寄存器的低位（bit 0~7）
      - 高字节地址（奇数）→ 寄存器的高位（bit 8~15）

    计算公式：
      寄存器地址 = 字节地址 ÷ 2（整数除法）
      寄存器内位号 = (1 - 字节地址 % 2) × 8 + 位号

    示例：
      字节地址=3, 位号=1 → Reg=1, bit_in_reg=(1-1)*8+1=1   → Reg 1 的第 1 位
      字节地址=2, 位号=1 → Reg=1, bit_in_reg=(1-0)*8+1=9   → Reg 1 的第 9 位

    :param byte_addr: 字节地址（从 Excel 解析得到）
    :param bit_num:   位号（0~7）
    :return:          (Modbus 寄存器地址, 寄存器内位号) 元组
    """
    reg = byte_addr // 2                                      # 字节地址 ÷ 2 = 寄存器地址（整数除法）
    bit_in_reg = (1 - byte_addr % 2) * 8 + bit_num           # 计算寄存器内位号
                                                             # 偶数字节 → 低位（bit 0~7）
                                                             # 奇数字节 → 高位（bit 8~15）
    return reg, bit_in_reg                                    # 返回 (寄存器地址, 寄存器内位号)


def load_register_map(filepath: str) -> dict:
    """
    从 Excel 文件加载变量映射表

    读取 TIA Portal 导出的 Modbus_Map.xlsx，逐行解析变量配置，
    生成程序内部使用的变量映射字典。

    返回的字典格式：
      普通变量：{modbus_addr(int): (dtype, name, desc, byte_addr, None)}
      位变量：  {modbus_addr.bit_in_reg(float): (bit_type, name, desc, byte_addr, bit_num)}

    位变量使用浮点数作为键的原因：
      同一个寄存器可能包含多个位变量（如 Reg 1 的 bit 0、bit 1、bit 9），
      使用浮点数键可以区分同一个寄存器内的不同位。

    :param filepath: Excel 文件路径，如 "Modbus_Map.xlsx"
    :return:         变量映射字典，失败或文件不存在时返回空字典 {}
    """
    if not Path(filepath).exists():                           # 检查文件是否存在
        print(f"变量表文件不存在: {filepath}")                 # 打印错误提示
        return {}                                             # 返回空字典

    wb = openpyxl.load_workbook(filepath, read_only=True)     # 以只读模式打开 Excel 文件（节省内存）
    ws = wb.active                                            # 获取活动工作表（第一个 Sheet）
    reg_map = {}                                              # 初始化映射字典

    for row in ws.iter_rows(min_row=2, values_only=True):     # 从第 2 行开始遍历（跳过表头行）
        # 读取 Excel 的 A、B、C 三列
        name, dtype_raw, byte_offset = row[0], row[1], row[2]

        if name is None or byte_offset is None:               # 跳过空行（变量名或地址为空）
            continue

        dtype_str = str(dtype_raw).strip().lower()            # 数据类型转为小写字符串，统一格式
        if "array" in dtype_str:                              # 跳过数组类型的父行（数组由多个子元素组成）
            continue

        base_dtype = TYPE_MAP.get(dtype_str)                  # 在映射表中查找对应的内部类型
        if base_dtype is None:                                # 未找到映射，说明是不支持的类型
            print(f"未知类型: {dtype_raw}，跳过 {name}")      # 打印警告，跳过此变量
            continue

        byte_addr, bit_num = _parse_byte_offset(byte_offset)  # 解析字节偏移，得到字节地址和位号

        if base_dtype == "bool16":                            # ===== Bool 变量处理 =====
            if bit_num is None:                               # 整数偏移的 Bool（未指定具体位）
                bit_num = 0                                   # 默认使用第 0 位
            reg, bit_in_reg = _byte_to_reg_bit(byte_addr, bit_num)  # 转换为 Modbus 寄存器地址和位号
            key = reg + bit_in_reg / 100.0                    # 生成浮点数键（如 1.09 表示 Reg 1 的第 9 位）
            reg_map[key] = (                                  # 存入映射字典
                f"bit_{bit_in_reg}",                          # 类型标识（如 "bit_9"）
                str(name).strip(),                            # 变量名（去除首尾空格）
                "",                                           # 描述（Excel 中未使用，暂为空）
                byte_addr,                                    # 原始字节地址
                bit_num                                       # 原始位号
            )
        else:                                                 # ===== 数值变量处理 =====
            addr = byte_addr // 2                             # 字节偏移 ÷ 2 = Modbus 寄存器地址
            reg_map[addr] = (                                 # 存入映射字典，键为整数地址
                base_dtype,                                   # 数据类型（如 "int16"、"float32"）
                str(name).strip(),                            # 变量名
                "",                                           # 描述（暂为空）
                byte_addr,                                    # 原始字节地址
                None                                          # 数值变量无位号
            )

    wb.close()                                                # 关闭 Excel 文件，释放系统资源
    return reg_map                                            # 返回完整的变量映射字典


def calc_read_range(reg_map: dict) -> tuple:
    """
    计算批量读取的 Modbus 起始地址和寄存器数量

    遍历所有变量，找出地址范围的最小值和最大值，
    从而确定一次批量读取需要从哪个地址开始、读取多少个寄存器。

    例如：变量表中有 Reg 0(int16)、Reg 1(float32)、Reg 3(int16)
      → 起始地址 = 0，结束地址 = 3 + 1 = 4，数量 = 4 - 0 = 4
      → 一次读取 Reg 0~3（共 4 个寄存器）

    :param reg_map: 变量映射字典
    :return:        (起始地址, 寄存器数量) 元组，空映射表返回 (0, 0)
    """
    if not reg_map:                                           # 映射表为空
        return 0, 0                                           # 返回 (0, 0)

    max_end = 0                                               # 记录最大结束地址
    for key, (dtype, *_) in reg_map.items():                  # 遍历所有变量
        addr = int(key)                                       # 获取整数地址（位变量取整数部分）
        if dtype.startswith("bit_"):                          # 位变量
            end = addr + 1                                    # 位变量占用 1 个寄存器
        else:                                                 # 数值变量
            cnt = DataType.REGISTER_COUNT.get(dtype, 1)       # 查询该类型占用的寄存器数
            end = addr + cnt                                  # 结束地址 = 起始地址 + 占用数
        max_end = max(max_end, end)                           # 更新最大结束地址

    start = min(int(k) for k in reg_map.keys())              # 所有变量中的最小地址 = 起始地址
    return start, max_end - start                             # 返回 (起始地址, 寄存器总数)


def parse_registers(all_regs: list, reg_start: int, reg_map: dict) -> dict:
    """
    将批量读取的原始寄存器值解析为 {变量键: 实际值} 字典

    根据变量映射表，从原始寄存器数组中提取对应位置的数据，
    然后根据数据类型调用 data_converter 模块进行类型转换。

    解析逻辑：
      位变量：从对应寄存器中提取指定位（bit），返回 True/False
      数值变量：根据类型占用的寄存器数，截取对应数量的寄存器值，然后转换

    :param all_regs:  原始寄存器值列表（由 Modbus 批量读取返回）
    :param reg_start: 批量读取的起始地址（用于计算数组索引）
    :param reg_map:   变量映射字典
    :return:          解析后的值字典 {变量键: 实际值}
    """
    result = {}                                               # 初始化结果字典

    for key, (dtype, *_) in reg_map.items():                  # 遍历所有变量
        addr = int(key)                                       # 获取整数地址
        idx = addr - reg_start                                # 计算在寄存器数组中的索引位置

        if dtype.startswith("bit_"):                          # ===== 位变量解析 =====
            bit_num = int(dtype.split("_")[1])                # 从类型标识中提取位号（如 "bit_9" → 9）
            if 0 <= idx < len(all_regs):                      # 索引在有效范围内
                # 通过位运算提取指定位：将寄存器值与 (1 << bit_num) 进行按位与
                # 例如 bit_num=9 时，1<<9=512，若该位为1则结果非零（True）
                result[key] = bool(all_regs[idx] & (1 << bit_num))
            else:                                             # 索引越界（寄存器数据不足）
                result[key] = None                            # 返回 None 表示读取失败

        else:                                                 # ===== 数值变量解析 =====
            cnt = DataType.REGISTER_COUNT.get(dtype, 1)       # 获取该类型占用的寄存器数
            try:
                data = all_regs[idx:idx + cnt]                # 从数组中截取对应数量的寄存器值
                if len(data) >= cnt:                          # 截取的数据完整（数量足够）
                    result[key] = convert_registers(data, dtype)  # 调用转换函数得到实际值
                else:                                         # 数据不完整（读取范围不够）
                    result[key] = None                        # 返回 None
            except (IndexError, ValueError):                  # 捕获索引越界或值转换异常
                result[key] = None                            # 异常时返回 None

    return result                                             # 返回完整的解析结果字典
