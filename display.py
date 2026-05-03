"""
终端显示模块
以表格形式打印采集到的数据
"""


def fmt_value(dtype: str, val) -> str:
    """
    格式化单个值为字符串，用于终端显示和 CSV 写入
    :param dtype: 数据类型字符串，如 "float32"、"bool16"
    :param val:   实际值（int/float/bool/None）
    :return:      格式化后的字符串
    """
    if val is None:                                     # 如果值为 None（读取失败）
        return "ERR"                                    # 返回错误标记
    if dtype == "float32":                              # 如果是浮点类型
        return f"{val:.1f}"                             # 保留一位小数
    if dtype == "bool16":                               # 如果是布尔类型
        return "true" if val else "false"               # true/false 小写显示
    return str(val)                                     # 其他类型直接转字符串


def print_table(values: dict, reg_map: dict):
    """
    以表格形式打印所有变量的当前值
    :param values:   解析后的值字典 {地址: 值}
    :param reg_map:  变量映射字典 {地址: (类型, 名称, 描述)}
    """
    print(f"{'变量名':<30} {'类型':<10} {'值':<15} {'描述'}")   # 打印表头，左对齐并指定列宽
    print("-" * 75)                                     # 打印分隔线
    for addr in sorted(reg_map.keys()):                 # 按地址顺序遍历所有变量
        dtype, name, desc = reg_map[addr]               # 解包获取类型、名称、描述
        print(f"{name:<30} {dtype:<10} {fmt_value(dtype, values.get(addr)):<15} {desc}")  # 打印一行数据
