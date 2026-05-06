"""
数据采集模块
封装 PLC 数据采集的核心逻辑，包括连接管理、数据读取、断线重连
提供统一的采集接口，简化 main.py 的主循环逻辑
"""

import time                                                   # 时间模块，用于延时
from datetime import datetime                                  # 时间模块，用于时间戳
from modbus_client import ModbusClient                         # Modbus 通讯客户端
from excel_reader import calc_read_range, parse_registers      # Excel 变量表工具


class DataAcquisition:
    """数据采集器类，封装采集循环和连接管理"""

    def __init__(self, plc_ip, plc_port, unit_id, timeout,
                 reconnect_delay, retry_delay):
        """
        初始化采集器参数

        :param plc_ip:          PLC 的 IP 地址
        :param plc_port:        Modbus TCP 端口号
        :param unit_id:         Modbus 从站地址
        :param timeout:         通讯超时时间（秒）
        :param reconnect_delay: 断线重连等待时间（秒）
        :param retry_delay:     重连失败后重试等待时间（秒）
        """
        self.plc_ip = plc_ip                                  # PLC IP 地址
        self.plc_port = plc_port                              # Modbus 端口
        self.unit_id = unit_id                                # 从站 ID
        self.timeout = timeout                                # 超时时间
        self.reconnect_delay = reconnect_delay                # 重连延迟
        self.retry_delay = retry_delay                        # 重试延迟
        self.client = None                                    # Modbus 客户端实例
        self.reg_map = None                                   # 变量映射表
        self.reg_start = 0                                    # 读取起始地址
        self.reg_count = 0                                    # 读取寄存器数量

    def load_map(self, map_file):
        """
        加载变量映射表

        :param map_file: Excel 变量表文件路径
        :return: True 加载成功，False 加载失败
        """
        from excel_reader import load_register_map            # 导入加载函数
        self.reg_map = load_register_map(map_file)            # 加载变量表
        if not self.reg_map:                                  # 变量表为空
            return False                                      # 返回失败
        self.reg_start, self.reg_count = calc_read_range(self.reg_map)  # 计算读取范围
        return True                                           # 返回成功

    def connect(self):
        """
        连接到 PLC

        :return: True 连接成功，False 连接失败
        """
        self.client = ModbusClient(                           # 创建 Modbus 客户端
            self.plc_ip, self.plc_port,                       # IP 和端口
            self.unit_id, self.timeout)                       # 从站 ID 和超时
        return self.client.connect()                          # 发起连接

    def disconnect(self):
        """断开与 PLC 的连接"""
        if self.client:                                       # 客户端已创建
            self.client.disconnect()                          # 断开连接
            self.client = None                                # 清空客户端

    def read_registers(self):
        """
        批量读取保持寄存器

        :return: 寄存器值列表，失败返回空列表
        """
        if not self.client:                                   # 未连接
            return []                                         # 返回空列表
        try:
            return self.client.read_holding_registers(        # 读取寄存器
                self.reg_start, self.reg_count)               # 起始地址和数量
        except Exception:                                     # 异常
            return []                                         # 返回空列表

    def parse_values(self, all_regs):
        """
        将原始寄存器值解析为实际值字典

        :param all_regs: 原始寄存器值列表
        :return: 解析后的值字典
        """
        return parse_registers(                               # 调用解析函数
            all_regs, self.reg_start, self.reg_map)           # 传入参数

    def reconnect(self):
        """
        尝试重新连接 PLC

        :return: True 重连成功，False 重连失败
        """
        self.disconnect()                                     # 断开旧连接
        time.sleep(self.reconnect_delay)                      # 等待重连延迟
        return self.connect()                                 # 尝试新连接

    def get_timestamp(self):
        """
        获取当前时间戳字符串

        :return: 格式化的时间戳（精确到毫秒）
        """
        return f"{datetime.now():%Y-%m-%d %H:%M:%S.%f}"[:-3]  # 生成时间戳
