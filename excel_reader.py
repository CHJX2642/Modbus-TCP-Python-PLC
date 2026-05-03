"""
Excel 变量表读取模块
从 TIA Portal 导出的 Modbus_Map.xlsx 读取变量配置
"""

from pathlib import Path                                # 用于检查文件是否存在
import openpyxl                                         # 用于读取 Excel 文件
from data_converter import DataType                     # 导入数据类型定义

# TIA Portal 数据类型名称 → 内部数据类型名称的映射表
TYPE_MAP = {
    "int": "int16",          # TIA 的 Int → 有符号16位整数
    "word": "uint16",        # TIA 的 Word → 无符号16位整数
    "dint": "int32",         # TIA 的 DInt → 有符号32位整数
    "dword": "uint32",       # TIA 的 DWord → 无符号32位整数
    "real": "float32",       # TIA 的 Real → 32位浮点数
    "bool": "bool16",        # TIA 的 Bool → 布尔值（读 WORD，256=true）
}


def load_register_map(filepath: str) -> dict:
    """
    从 TIA Portal 导出的 Excel 读取变量表
    格式：列A=变量名, 列B=数据类型, 列C=字节偏移
    返回：{ Modbus地址: (数据类型, 变量名, 描述) }
    """
    if not Path(filepath).exists():                     # 检查文件是否存在
        print(f"变量表文件不存在: {filepath}")           # 文件不存在则打印提示
        return {}                                       # 返回空字典

    wb = openpyxl.load_workbook(filepath, read_only=True)  # 以只读模式打开 Excel
    ws = wb.active                                      # 获取活动工作表
    reg_map = {}                                        # 存储解析结果的字典

    for row in ws.iter_rows(min_row=2, values_only=True):  # 从第2行开始遍历（跳过表头）
        name, dtype_raw, byte_offset = row[0], row[1], row[2]  # 读取三列数据
        if name is None or byte_offset is None:         # 如果变量名或偏移为空
            continue                                    # 跳过该行

        dtype_str = str(dtype_raw).strip().lower()      # 将数据类型转为小写并去除空格
        if "array" in dtype_str:                        # 如果是数组父行（如 Array[0..9] of Int）
            continue                                    # 跳过，只处理数组元素行

        dtype = TYPE_MAP.get(dtype_str)                 # 在映射表中查找内部类型名
        if dtype is None:                               # 如果找不到对应类型
            print(f"未知类型: {dtype_raw}，跳过 {name}")  # 打印警告信息
            continue                                    # 跳过该变量

        addr = int(byte_offset) // 2                    # 字节偏移除以2得到 Modbus 地址
        reg_map[addr] = (dtype, str(name).strip(), "")  # 存入字典，描述暂为空

    wb.close()                                          # 关闭 Excel 文件
    return reg_map                                      # 返回变量映射字典


def calc_read_range(reg_map: dict) -> tuple:
    """
    计算批量读取的起始地址和寄存器数量
    :param reg_map: 变量映射字典 {地址: (类型, 名称, 描述)}
    :return: (起始地址, 读取数量)
    """
    if not reg_map:                                     # 如果变量表为空
        return 0, 0                                     # 返回 0, 0
    start = min(reg_map.keys())                         # 获取最小地址作为起始地址
    max_count = 0                                       # 记录需要读取的最大寄存器数
    for addr, (dtype, _, _) in reg_map.items():         # 遍历所有变量
        count = DataType.REGISTER_COUNT.get(dtype, 1)   # 获取该类型占用的寄存器数
        max_count = max(max_count, addr - start + count) # 更新最大偏移量
    return start, max_count                             # 返回起始地址和读取数量
