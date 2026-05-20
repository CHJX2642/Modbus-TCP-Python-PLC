"""
终端显示模块

功能概述：
  以格式化表格的形式在终端打印采集到的数据，用于实时监控 PLC 变量状态。
  每次采集后覆盖上一次的输出，实现终端原地刷新效果（不产生滚动）。

终端刷新原理：
  使用 ANSI 转义码 \033[NA 将光标上移 N 行，然后重新打印新数据覆盖旧数据。
  N = 变量数量 + DISPLAY_LINES_OFFSET（表头1行 + 分隔线1行 + 空行1行）。
  这样用户看到的是同一位置的数据在不断更新，而不是屏幕不断滚动。

显示效果示例：
  [2026-05-20 14:30:15.123]
  变量名                          偏移量       类型       值              描述
  --------------------------------------------------------------------------------
  温度1                           字节0        int16      25.3           ℃
  压力                            字节2        float32    1.5            bar
  电机运行                        字节4.位0    bit_0      true
"""


def fmt_value(dtype: str, val) -> str:
    """
    将单个变量值格式化为显示字符串

    根据数据类型选择合适的显示格式：
      - float32：保留 1 位小数（如 25.3）
      - bool16 / bit_*：显示 true 或 false（小写）
      - 其他类型：直接转为字符串
      - None（读取失败）：显示 ERR

    :param dtype: 数据类型字符串（如 "int16"、"float32"、"bool16"、"bit_9"）
    :param val:   变量的实际值（int / float / bool / None）
    :return:      格式化后的显示字符串
    """
    if val is None:                                            # 读取失败，值为 None
        return "ERR"                                           # 返回错误标记
    if dtype == "float32":                                     # 浮点数类型
        return f"{val:.1f}"                                    # 保留 1 位小数，如 "25.3"
    if dtype == "bool16" or dtype.startswith("bit_"):          # 布尔类型（普通 Bool 或位变量）
        return "true" if val else "false"                      # 显示小写的 true / false
    return str(val)                                            # 其他类型（int16/uint16/int32/uint32）直接转字符串


def print_table(values: dict, reg_map: dict):
    """
    以表格形式打印所有变量的当前值

    表格格式：
      变量名（左对齐30字符） | 偏移量（左对齐12字符） | 类型（左对齐10字符） | 值（左对齐15字符） | 描述

    位变量的偏移量显示为 "字节X.位Y"（如 "字节4.位0"）
    数值变量的偏移量显示为 "字节X"（如 "字节2"）

    :param values:  解析后的值字典 {变量键: 实际值}，由 parse_registers() 返回
    :param reg_map: 变量映射字典 {地址: (类型, 名称, 描述, 字节地址, 位号)}
    """
    # 打印表头行
    print(f"{'变量名':<30} {'偏移量':<12} {'类型':<10} {'值':<15} {'描述'}")
    print("-" * 80)                                            # 打印 80 个字符的分隔线

    for addr in sorted(reg_map.keys()):                        # 按地址从小到大排序遍历
        dtype, name, desc, byte_addr, bit_num = reg_map[addr]  # 解包变量信息

        # 构建偏移量显示字符串
        if bit_num is not None:                                # 位变量（有位号）
            offset = f"字节{byte_addr}.位{bit_num}"            # 格式："字节4.位0"
        else:                                                  # 数值变量（无位号）
            offset = f"字节{byte_addr}"                        # 格式："字节2"

        # 打印一行变量信息
        # 使用 f-string 的 <:30 等格式控制对齐宽度
        print(f"{name:<30} {offset:<12} {dtype:<10} "
              f"{fmt_value(dtype, values.get(addr)):<15} {desc}")
