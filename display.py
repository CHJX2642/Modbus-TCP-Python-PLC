"""
终端显示模块
以表格形式打印采集到的数据，用于终端实时监控
"""


def fmt_value(dtype: str, val) -> str:
    """
    将单个值格式化为字符串，用于终端显示和 CSV 写入

    :param dtype: 数据类型字符串（如 "float32"、"bool16"、"bit_3"）
    :param val:   实际值（int/float/bool/None）
    :return:      格式化后的字符串
    """
    if val is None:                                            # 值为空（读取失败）
        return "ERR"                                           # 返回错误标记
    if dtype == "float32":                                     # 浮点类型
        return f"{val:.1f}"                                    # 保留 1 位小数
    if dtype == "bool16" or dtype.startswith("bit_"):          # 布尔类型
        return "true" if val else "false"                      # 返回 true/false
    return str(val)                                            # 其他类型直接转字符串


def print_table(values: dict, reg_map: dict):
    """
    以表格形式打印所有变量的当前值

    :param values:   解析后的值字典 {地址: 值}
    :param reg_map:  变量映射字典 {地址: (类型, 名称, 描述, 字节地址, 位号)}
    """
    # 打印表头
    print(f"{'变量名':<30} {'偏移量':<12} {'类型':<10} {'值':<15} {'描述'}")
    print("-" * 80)                                            # 打印分隔线

    # 按地址顺序遍历变量
    for addr in sorted(reg_map.keys()):
        dtype, name, desc, byte_addr, bit_num = reg_map[addr]  # 解包变量信息

        # 格式化偏移量显示
        if bit_num is not None:                                # 有位号（布尔类型）
            offset_str = f"字节{byte_addr}.位{bit_num}"        # 格式为"字节X.位Y"
        else:                                                  # 无位号（数值类型）
            offset_str = f"字节{byte_addr}"                    # 格式为"字节X"

        # 打印一行变量信息
        print(f"{name:<30} {offset_str:<12} {dtype:<10} "
              f"{fmt_value(dtype, values.get(addr)):<15} {desc}")
