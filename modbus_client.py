"""
Modbus TCP 客户端模块

功能概述：
  封装与西门子 PLC 的 Modbus TCP 通信功能，提供连接管理和读写操作。
  基于 pymodbus 库实现，支持标准 Modbus TCP 协议。

支持的功能码（Function Code）：
  读操作：
    FC 0x01 — 读取线圈（Coils）          可读可写，用于 BOOL 开关量输出
    FC 0x02 — 读取离散输入（DI）          只读，用于 BOOL 传感器信号输入
    FC 0x03 — 读取保持寄存器（Holding Reg） 可读可写，用于 WORD/FLOAT 数据（最常用）
    FC 0x04 — 读取输入寄存器（Input Reg）  只读，用于模拟量采集

  写操作：
    FC 0x05 — 写入单个线圈               控制单个 BOOL 输出
    FC 0x06 — 写入单个保持寄存器          写入单个 WORD/DINT/REAL 数据
    FC 0x10 — 写入多个保持寄存器          批量写入多个寄存器（如写入一个 FLOAT32 需要2个寄存器）

使用方式：
  client = ModbusClient("192.168.0.99", 502, 1)
  client.connect()
  regs = client.read_holding_registers(0, 10)  # 从地址0读取10个寄存器
  client.disconnect()
"""

from pymodbus.client import ModbusTcpClient                   # 导入 pymodbus 的 Modbus TCP 客户端类
from pymodbus.exceptions import ModbusException                # 导入 Modbus 协议异常类，用于捕获通讯错误


class ModbusClient:
    """
    Modbus TCP 客户端类

    职责：
      - 管理与 PLC 的 TCP 连接（建立、断开）
      - 提供所有 Modbus 读写操作的封装方法
      - 统一处理异常，返回安全的默认值（空列表或 False）

    注意事项：
      - 所有方法在未连接时都会安全返回默认值，不会抛出异常
      - 所有读写操作都通过 device_id（从站 ID）指定目标 PLC
    """

    def __init__(self, ip: str, port: int, unit_id: int, timeout: int = 3):
        """
        初始化客户端参数（此时并不建立连接，需要手动调用 connect()）

        :param ip:       PLC 的 IP 地址，如 "192.168.0.99"
        :param port:     Modbus TCP 端口号，西门子 PLC 默认为 502
        :param unit_id:  从站地址（Unit ID），用于区分同一网络上的多台 PLC，默认为 1
        :param timeout:  TCP 连接超时时间（秒），超时则认为 PLC 不可达，默认为 3 秒
        """
        self.ip = ip                                          # 保存 PLC 的 IP 地址
        self.port = port                                      # 保存 Modbus TCP 端口号
        self.unit_id = unit_id                                # 保存从站 ID
        self.timeout = timeout                                # 保存超时时间
        self.client = None                                    # pymodbus 客户端实例，初始为 None（未连接状态）

    def connect(self) -> bool:
        """
        建立与 PLC 的 TCP 连接

        工作流程：
          1. 创建 pymodbus 的 ModbusTcpClient 实例
          2. 调用 connect() 方法发起 TCP 三次握手
          3. 返回连接结果

        :return: True 表示连接成功，False 表示连接失败（网络不通、PLC 关机等）
        """
        try:
            self.client = ModbusTcpClient(                    # 创建 pymodbus 客户端实例
                host=self.ip,                                 # 设置 PLC 的 IP 地址
                port=self.port,                               # 设置 Modbus TCP 端口号
                timeout=self.timeout                          # 设置超时时间（秒）
            )
            return self.client.connect()                      # 发起 TCP 连接，返回 True/False
        except Exception as e:                                # 捕获所有异常（网络错误、参数错误等）
            print(f"连接失败: {e}")                            # 打印具体错误信息，方便排查
            return False                                      # 返回连接失败

    def disconnect(self):
        """
        断开与 PLC 的连接，释放 TCP 连接资源

        安全性：如果当前未连接（client 为 None），调用此方法不会报错
        """
        if self.client:                                       # 如果客户端实例存在（已连接状态）
            self.client.close()                               # 关闭 TCP 连接，释放系统资源
            self.client = None                                # 将客户端实例置为 None，标记为未连接状态

    def read_holding_registers(self, address: int, count: int) -> list:
        """
        FC 0x03 — 读取保持寄存器（Holding Registers）

        这是最常用的读取方法，用于读取 PLC 中的 WORD、DINT、REAL 等数据。
        保持寄存器是可读可写的，地址范围通常为 40001~49999（或 0~9999）。

        每个寄存器为 16 位（2 字节），数据类型与寄存器数量的对应关系：
          - int16 / uint16 / bool16 → 1 个寄存器
          - int32 / uint32 / float32 → 2 个寄存器（高字在前，低字在后）

        :param address: 起始寄存器地址（从 0 开始计数）
        :param count:   要读取的寄存器数量
        :return:        寄存器值列表（每个元素为 0~65535 的整数），失败返回空列表 []
        """
        if not self.client:                                   # 未连接，无法读取
            return []                                         # 返回空列表表示失败
        try:
            result = self.client.read_holding_registers(      # 发送 Modbus FC03 读取请求
                address=address,                              # 起始寄存器地址
                count=count,                                  # 读取的寄存器数量
                device_id=self.unit_id                        # 目标从站 ID
            )
            if result.isError():                              # 检查 PLC 响应是否包含错误码
                return []                                     # 响应出错（地址越界、PLC 错误等），返回空列表
            return list(result.registers)                     # 成功：将寄存器值从 tuple 转为 list 返回
        except ModbusException:                               # 捕获 Modbus 协议层异常（超时、连接断开等）
            return []                                         # 异常时返回空列表，由调用方判断失败

    def read_coils(self, address: int, count: int) -> list:
        """
        FC 0x01 — 读取线圈（Coils）

        线圈是可读可写的位（BOOL）变量，对应 PLC 的输出点（如 Q0.0、Q0.1）。
        每个线圈占 1 位（bit），返回值为 True（通）或 False（断）。

        :param address: 起始线圈地址（从 0 开始计数）
        :param count:   要读取的线圈数量
        :return:        布尔值列表（True/False），失败返回空列表 []
        """
        if not self.client:                                   # 未连接，无法读取
            return []                                         # 返回空列表
        try:
            result = self.client.read_coils(                  # 发送 Modbus FC01 读取请求
                address=address,                              # 起始线圈地址
                count=count,                                  # 读取的线圈数量
                device_id=self.unit_id                        # 目标从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.bits[:count])                  # 从位数组中截取前 count 个位，转为列表返回
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def read_discrete_inputs(self, address: int, count: int) -> list:
        """
        FC 0x02 — 读取离散输入（Discrete Inputs）

        离散输入是只读的位（BOOL）变量，对应 PLC 的输入点（如 I0.0、I0.1）。
        与线圈（Coils）的区别：离散输入只读，线圈可读可写。

        :param address: 起始离散输入地址（从 0 开始计数）
        :param count:   要读取的离散输入数量
        :return:        布尔值列表（True/False），失败返回空列表 []
        """
        if not self.client:                                   # 未连接，无法读取
            return []                                         # 返回空列表
        try:
            result = self.client.read_discrete_inputs(        # 发送 Modbus FC02 读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 目标从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.bits[:count])                  # 截取并返回布尔值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def read_input_registers(self, address: int, count: int) -> list:
        """
        FC 0x04 — 读取输入寄存器（Input Registers）

        输入寄存器是只读的 16 位数据，通常用于模拟量采集（如温度、压力传感器）。
        与保持寄存器（Holding Registers）的区别：输入寄存器只读，保持寄存器可读可写。

        :param address: 起始输入寄存器地址（从 0 开始计数）
        :param count:   要读取的寄存器数量
        :return:        寄存器值列表（0~65535 的整数），失败返回空列表 []
        """
        if not self.client:                                   # 未连接，无法读取
            return []                                         # 返回空列表
        try:
            result = self.client.read_input_registers(        # 发送 Modbus FC04 读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 目标从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.registers)                     # 返回寄存器值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def write_register(self, address: int, value: int) -> bool:
        """
        FC 0x06 — 写入单个保持寄存器

        将一个 16 位的值写入 PLC 的指定保持寄存器地址。
        适用于写入 WORD、BOOL（用 0/256 表示）等单寄存器数据。

        :param address: 目标寄存器地址
        :param value:   要写入的值（0~65535 的整数）
        :return:        True 表示写入成功，False 表示写入失败
        """
        if not self.client:                                   # 未连接，无法写入
            return False                                      # 返回失败
        try:
            result = self.client.write_register(              # 发送 Modbus FC06 写入请求
                address=address,                              # 目标寄存器地址
                value=value,                                  # 要写入的 16 位值
                device_id=self.unit_id                        # 目标从站 ID
            )
            return not result.isError()                       # 无错误则返回 True（写入成功）
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败

    def write_registers(self, address: int, values: list) -> bool:
        """
        FC 0x10 — 写入多个保持寄存器（批量写入）

        一次写入多个连续的寄存器，适用于写入 32 位数据（int32/uint32/float32 需要2个寄存器）。
        例如写入一个 float32：将浮点数拆分为2个16位寄存器值，一次性写入。

        :param address: 起始寄存器地址
        :param values:  要写入的值列表（如 [0x1234, 0x5678]）
        :return:        True 表示写入成功，False 表示写入失败
        """
        if not self.client:                                   # 未连接，无法写入
            return False                                      # 返回失败
        try:
            result = self.client.write_registers(             # 发送 Modbus FC10 批量写入请求
                address=address,                              # 起始寄存器地址
                values=values,                                # 要写入的值列表
                device_id=self.unit_id                        # 目标从站 ID
            )
            return not result.isError()                       # 无错误则返回 True
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败

    def write_coil(self, address: int, value: bool) -> bool:
        """
        FC 0x05 — 写入单个线圈

        控制 PLC 的一个 BOOL 输出点（如 Q0.0）的通断状态。
        True = 线圈得电（ON），False = 线圈失电（OFF）。

        :param address: 目标线圈地址
        :param value:   True（得电/ON）或 False（失电/OFF）
        :return:        True 表示写入成功，False 表示写入失败
        """
        if not self.client:                                   # 未连接，无法写入
            return False                                      # 返回失败
        try:
            result = self.client.write_coil(                  # 发送 Modbus FC05 写入请求
                address=address,                              # 目标线圈地址
                value=value,                                  # 写入值（True/False）
                device_id=self.unit_id                        # 目标从站 ID
            )
            return not result.isError()                       # 无错误则返回 True
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败
