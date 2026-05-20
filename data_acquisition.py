"""
数据采集器模块

功能概述：
  封装 PLC 数据采集的全部核心逻辑，作为 main.py 和底层通讯模块之间的桥梁。
  main.py 只需要调用本模块提供的方法，无需关心 Modbus 协议细节。

职责：
  1. 初始化采集参数（IP、端口、从站 ID 等）
  2. 加载 Excel 变量表，计算 Modbus 读取范围
  3. 建立和断开 PLC 连接
  4. 批量读取寄存器并解析为实际值
  5. 断线自动重连

调用流程（由 main.py 驱动）：
  collector = DataAcquisition(...)   → 创建采集器
  collector.load_map(file)           → 加载变量表
  collector.connect()                → 连接 PLC
  while running:
      regs = collector.read_registers()   → 读取寄存器
      values = collector.parse_values()   → 解析为实际值
      ... 显示和存储 ...
  collector.disconnect()             → 断开连接
"""

import time                                                   # 时间模块，用于重连等待
from datetime import datetime                                  # 时间模块，用于生成时间戳
from modbus_client import ModbusClient                         # Modbus TCP 客户端
from excel_reader import load_register_map, calc_read_range, parse_registers  # Excel 变量表工具


class DataAcquisition:
    """
    数据采集器类

    封装了从 PLC 采集数据的全部逻辑，提供简洁的对外接口。
    main.py 通过此类与 PLC 交互，无需直接操作 Modbus 协议。
    """

    def __init__(self, plc_ip, plc_port, unit_id, timeout, reconnect_delay, retry_delay):
        """
        初始化采集器参数

        所有参数都从 main.py 的配置区传入，用户只需修改 main.py 即可调整。

        :param plc_ip:          PLC 的 IP 地址，如 "192.168.0.99"
        :param plc_port:        Modbus TCP 端口号，西门子 PLC 默认 502
        :param unit_id:         Modbus 从站 ID（Unit ID），默认 1
        :param timeout:         TCP 通讯超时时间（秒），超时则认为 PLC 不可达
        :param reconnect_delay: 连接断开后等待多久再重连（秒），给 PLC 响应时间
        :param retry_delay:     重连失败后等待多久再重试（秒），避免频繁重连
        """
        self.plc_ip = plc_ip                                  # PLC 的 IP 地址
        self.plc_port = plc_port                              # Modbus TCP 端口号
        self.unit_id = unit_id                                # 从站 ID
        self.timeout = timeout                                # 通讯超时秒数
        self.reconnect_delay = reconnect_delay                # 断线重连等待秒数
        self.retry_delay = retry_delay                        # 重连失败重试等待秒数
        self.client = None                                    # Modbus 客户端实例，初始为 None（未连接）
        self.reg_map = None                                   # 变量映射表，初始为 None（未加载）
        self.reg_start = 0                                    # 批量读取的起始 Modbus 地址
        self.reg_count = 0                                    # 需要读取的寄存器总数

    def load_map(self, map_file):
        """
        加载 Excel 变量表

        从 TIA Portal 导出的 Modbus_Map.xlsx 中读取变量配置，
        解析出每个变量的名称、数据类型、字节地址等信息，
        并自动计算出批量读取所需的 Modbus 地址范围。

        :param map_file: Excel 变量表文件路径，如 "Modbus_Map.xlsx"
        :return:         True 表示加载成功，False 表示文件不存在或变量表为空
        """
        self.reg_map = load_register_map(map_file)            # 从 Excel 加载变量映射表
        if not self.reg_map:                                  # 变量表为空（文件不存在或无有效数据）
            return False                                      # 返回加载失败
        # 根据变量映射表计算批量读取的起始地址和寄存器数量
        self.reg_start, self.reg_count = calc_read_range(self.reg_map)
        return True                                           # 返回加载成功

    def connect(self):
        """
        连接到 PLC

        创建 Modbus 客户端实例并发起 TCP 连接。
        连接成功后，可以调用 read_registers() 读取数据。

        :return: True 表示连接成功，False 表示连接失败（PLC 不在线或网络不通）
        """
        self.client = ModbusClient(                           # 创建 Modbus TCP 客户端实例
            self.plc_ip,                                      # PLC IP 地址
            self.plc_port,                                    # Modbus TCP 端口
            self.unit_id,                                     # 从站 ID
            self.timeout                                      # 超时秒数
        )
        return self.client.connect()                          # 发起 TCP 连接，返回 True/False

    def disconnect(self):
        """
        断开与 PLC 的连接

        安全方法：如果当前未连接（client 为 None），调用此方法不会报错。
        断开后需要重新调用 connect() 才能继续读取数据。
        """
        if self.client:                                       # 如果客户端实例存在（已连接）
            self.client.disconnect()                          # 调用客户端的断开方法，关闭 TCP 连接
            self.client = None                                # 置为 None，标记为未连接状态

    def read_registers(self):
        """
        批量读取所有保持寄存器

        一次性读取变量表中定义的所有寄存器（从 reg_start 开始，共 reg_count 个）。
        返回的原始寄存器值列表需要通过 parse_values() 解析为实际值。

        :return: 寄存器值列表（每个元素为 0~65535 的整数），失败返回空列表 []
        """
        if not self.client:                                   # 未连接 PLC
            return []                                         # 返回空列表
        try:
            return self.client.read_holding_registers(        # 调用客户端的读取方法
                self.reg_start,                               # 起始地址
                self.reg_count                                # 读取数量
            )
        except Exception:                                     # 捕获所有异常（网络错误、超时等）
            return []                                         # 异常时返回空列表

    def parse_values(self, all_regs):
        """
        将原始寄存器值解析为实际值字典

        调用 excel_reader 模块的 parse_registers() 函数，
        根据变量映射表将原始寄存器值转换为对应数据类型的实际值。

        :param all_regs: 原始寄存器值列表（由 read_registers() 返回）
        :return:         解析后的值字典 {变量键: 实际值}
                         例如：{0: 100, 1: 3.14, 1.09: True}
        """
        return parse_registers(                               # 调用解析函数
            all_regs,                                         # 原始寄存器值
            self.reg_start,                                   # 起始地址
            self.reg_map                                      # 变量映射表
        )

    def reconnect(self):
        """
        断线重连

        执行流程：
          1. 断开当前（可能已失效的）连接
          2. 等待 reconnect_delay 秒（给网络和 PLC 恢复时间）
          3. 重新发起 TCP 连接

        :return: True 表示重连成功，False 表示重连失败
        """
        self.disconnect()                                     # 先断开旧连接（释放可能残留的资源）
        time.sleep(self.reconnect_delay)                      # 等待指定秒数，让网络恢复
        return self.connect()                                 # 尝试建立新连接

    def get_timestamp(self):
        """
        获取当前时间戳字符串

        格式：2026-05-20 14:30:15.123
        精确到毫秒，用于终端显示和 CSV 记录。

        :return: 格式化的时间戳字符串
        """
        return f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3] # 取完整时间戳的前 23 位（去掉微秒最后 3 位）
