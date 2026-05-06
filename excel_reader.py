"""
Excel 变量表读取模块
从 TIA Portal 导出的 Modbus_Map.xlsx 读取变量配置
支持位寻址：字节偏移的小数部分表示位号（如 0.1 = 字节0的第1位）

Modbus 寄存器与字节的映射关系（标准大端序）：
  Reg N = 字节 (2N) 的高字节 + 字节 (2N+1) 的低字节
  例：Reg 0 = 字节0(高) + 字节1(低)，Reg 1 = 字节2(高) + 字节3(低)
"""

from pathlib import Path                                      # 路径处理模块
import openpyxl                                               # Excel 读写库
from data_converter import DataType, convert_registers        # 数据类型和转换函数


# ======================== 类型映射表 ========================
TYPE_MAP = {
    "int": "int16",                                           # TIA Portal Int → 16位有符号整数
    "word": "uint16",                                         # TIA Portal Word → 16位无符号整数
    "dint": "int32",                                          # TIA Portal DInt → 32位有符号整数
    "dword": "uint32",                                        # TIA Portal DWord → 32位无符号整数
    "real": "float32",                                        # TIA Portal Real → 32位浮点数
    "bool": "bool16",                                         # TIA Portal Bool → 布尔值
}


def _parse_byte_offset(raw) -> tuple:
    """
    解析字节偏移值
    - 整数（40）→ (40, None)      普通变量
    - 小数（0.1）→ (0, 1)         字节0的第1位
    - 小数（3.7）→ (3, 7)         字节3的第7位

    :param raw: 原始偏移值（整数或浮点数）
    :return: (字节地址, 位号) 元组，位号为 None 表示非位寻址
    """
    val = float(raw)                                          # 转为浮点数
    byte_addr = int(val)                                      # 整数部分为字节地址
    frac = val - byte_addr                                    # 计算小数部分
    if frac > 0.001:                                          # 有小数部分
        return byte_addr, round(frac * 10)                    # 返回位号（四舍五入）
    return byte_addr, None                                    # 无位号


def _byte_to_reg_bit(byte_addr: int, bit_num: int) -> tuple:
    """
    将 (字节地址, 位号) 转换为 (Modbus寄存器地址, 寄存器内位号)

    Siemens PLC 字节序：
      低字节地址 → 寄存器低位 (bits 0-7)
      高字节地址 → 寄存器高位 (bits 8-15)

    计算公式：
      寄存器地址 = 字节地址 // 2
      寄存器内位号 = (1 - 字节地址 % 2) * 8 + 位号

    示例：
      字节3的第1位 → Reg 1 的第 1 位
      字节2的第1位 → Reg 1 的第 9 位

    :param byte_addr: 字节地址
    :param bit_num:   位号（0-7）
    :return: (寄存器地址, 寄存器内位号) 元组
    """
    reg = byte_addr // 2                                      # 计算寄存器地址
    bit_in_reg = (1 - byte_addr % 2) * 8 + bit_num           # 计算寄存器内位号
    return reg, bit_in_reg                                    # 返回元组


def load_register_map(filepath: str) -> dict:
    """
    从 Excel 文件加载变量映射表

    返回字典格式：
      普通变量: {modbus_addr(int): (dtype, name, desc, byte_addr, None)}
      位寻址Bool: {modbus_addr.bit_in_reg(float): (bit_type, name, desc, byte_addr, bit_num)}

    示例：
      字节3的第1位 → 寄存器1的第9位 → {1.09: ("bit_9", "xxx", "", 3, 1)}

    :param filepath: Excel 文件路径
    :return: 变量映射字典
    """
    if not Path(filepath).exists():                            # 检查文件是否存在
        print(f"变量表文件不存在: {filepath}")                 # 打印错误信息
        return {}                                              # 返回空字典

    wb = openpyxl.load_workbook(filepath, read_only=True)      # 打开 Excel 文件（只读模式）
    ws = wb.active                                             # 获取活动工作表
    reg_map = {}                                               # 初始化映射字典

    for row in ws.iter_rows(min_row=2, values_only=True):      # 从第2行开始遍历（跳过表头）
        name, dtype_raw, byte_offset = row[0], row[1], row[2]  # 读取变量名、类型、偏移
        if name is None or byte_offset is None:                # 跳过空行
            continue

        dtype_str = str(dtype_raw).strip().lower()             # 转为小写字符串
        if "array" in dtype_str:                               # 跳过数组父行
            continue

        base_dtype = TYPE_MAP.get(dtype_str)                   # 查找类型映射
        if base_dtype is None:                                 # 未知类型
            print(f"未知类型: {dtype_raw}，跳过 {name}")       # 打印警告
            continue

        byte_addr, bit_num = _parse_byte_offset(byte_offset)   # 解析字节偏移

        if base_dtype == "bool16":                             # Bool 变量处理
            if bit_num is None:                                # 整数偏移
                bit_num = 0                                    # 默认为第0位
            reg, bit_in_reg = _byte_to_reg_bit(byte_addr, bit_num)  # 转换为寄存器地址和位号
            key = reg + bit_in_reg / 100.0                     # 生成浮点数键
            reg_map[key] = (                                   # 存储到映射表
                f"bit_{bit_in_reg}",                           # 类型标识
                str(name).strip(),                             # 变量名
                "",                                            # 描述（暂空）
                byte_addr,                                     # 字节地址
                bit_num                                        # 原始位号
            )
        else:                                                  # 非 Bool 变量处理
            addr = byte_addr // 2                              # 字节偏移 ÷ 2 = Modbus 地址
            reg_map[addr] = (                                  # 存储到映射表
                base_dtype,                                    # 数据类型
                str(name).strip(),                             # 变量名
                "",                                            # 描述（暂空）
                byte_addr,                                     # 字节地址
                None                                           # 无位号
            )

    wb.close()                                                 # 关闭 Excel 文件
    return reg_map                                             # 返回映射字典


def calc_read_range(reg_map: dict) -> tuple:
    """
    计算批量读取的 Modbus 起始地址和寄存器数量

    :param reg_map: 变量映射字典
    :return: (起始地址, 寄存器数量) 元组
    """
    if not reg_map:                                            # 映射表为空
        return 0, 0                                            # 返回 (0, 0)

    max_end = 0                                                # 最大结束地址
    for key, (dtype, *_) in reg_map.items():                   # 遍历所有变量
        addr = int(key)                                        # 获取整数地址
        if dtype.startswith("bit_"):                           # 位变量
            end = addr + 1                                     # 占用1个寄存器
        else:                                                  # 数值变量
            cnt = DataType.REGISTER_COUNT.get(dtype, 1)        # 获取占用寄存器数
            end = addr + cnt                                   # 计算结束地址
        max_end = max(max_end, end)                            # 更新最大结束地址

    start = min(int(k) for k in reg_map.keys())               # 获取最小起始地址
    return start, max_end - start                              # 返回起始地址和数量


def parse_registers(all_regs: list, reg_start: int, reg_map: dict) -> dict:
    """
    将批量读取的原始寄存器值解析为 {key: 实际值}

    :param all_regs:   原始寄存器值列表（由 Modbus 返回）
    :param reg_start:  起始地址
    :param reg_map:    变量映射字典
    :return: 解析后的值字典
    """
    result = {}                                                # 结果字典
    for key, (dtype, *_) in reg_map.items():                   # 遍历所有变量
        addr = int(key)                                        # 获取整数地址
        idx = addr - reg_start                                 # 计算在数组中的索引

        if dtype.startswith("bit_"):                           # 位变量处理
            bit_num = int(dtype.split("_")[1])                 # 提取位号
            if 0 <= idx < len(all_regs):                       # 索引有效
                result[key] = bool(all_regs[idx] & (1 << bit_num))  # 提取指定位
            else:                                              # 索引越界
                result[key] = None                             # 返回 None
        else:                                                  # 数值变量处理
            cnt = DataType.REGISTER_COUNT.get(dtype, 1)        # 获取占用寄存器数
            try:
                data = all_regs[idx:idx + cnt]                 # 提取寄存器数据
                if len(data) >= cnt:                           # 数据完整
                    result[key] = convert_registers(data, dtype)  # 转换为实际值
                else:                                          # 数据不完整
                    result[key] = None                         # 返回 None
            except (IndexError, ValueError):                   # 异常处理
                result[key] = None                             # 返回 None

    return result                                              # 返回结果字典
