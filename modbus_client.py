"""
Modbus TCP 客户端模块
封装与西门子 PLC 的 Modbus TCP 通信功能
支持四种读功能码：FC01 线圈、FC02 离散输入、FC03 保持寄存器、FC04 输入寄存器
支持三种写功能码：FC05 单线圈、FC06 单寄存器、FC10 多寄存器
"""

from pymodbus.client import ModbusTcpClient                   # 导入 Modbus TCP 客户端
from pymodbus.exceptions import ModbusException                # 导入 Modbus 异常类


class ModbusClient:
    """Modbus TCP 客户端类，封装连接管理和读写操作"""

    def __init__(self, ip: str, port: int, unit_id: int, timeout: int = 3):
        """
        初始化客户端参数

        :param ip:       PLC 的 IP 地址
        :param port:     Modbus TCP 端口号（默认 502）
        :param unit_id:  从站地址（Unit ID）
        :param timeout:  连接超时时间（秒）
        """
        self.ip = ip                                          # 保存 IP 地址
        self.port = port                                      # 保存端口号
        self.unit_id = unit_id                                # 保存从站 ID
        self.timeout = timeout                                # 保存超时时间
        self.client = None                                    # pymodbus 客户端实例，初始为空

    def connect(self) -> bool:
        """
        连接到 PLC

        :return: True 连接成功，False 连接失败
        """
        try:
            self.client = ModbusTcpClient(                    # 创建 pymodbus 客户端
                host=self.ip,                                 # 设置 IP 地址
                port=self.port,                               # 设置端口号
                timeout=self.timeout                          # 设置超时时间
            )
            return self.client.connect()                      # 发起 TCP 连接并返回结果
        except Exception as e:                                # 捕获所有异常
            print(f"连接失败: {e}")                            # 打印错误信息
            return False                                      # 返回失败

    def disconnect(self):
        """断开与 PLC 的连接，释放资源"""
        if self.client:                                       # 如果客户端已创建
            self.client.close()                               # 关闭 TCP 连接
            self.client = None                                # 清空客户端实例

    def read_holding_registers(self, address: int, count: int) -> list:
        """
        FC 0x03 读取保持寄存器（可读可写，用于 WORD/FLOAT 数据）

        :param address: 起始地址
        :param count:   读取数量
        :return:        寄存器值列表，失败返回空列表
        """
        if not self.client:                                   # 未连接则返回空
            return []
        try:
            result = self.client.read_holding_registers(      # 发送读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.registers)                     # 返回寄存器值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def read_coils(self, address: int, count: int) -> list:
        """
        FC 0x01 读取线圈（可读可写，用于 BOOL 开关量）

        :param address: 起始地址
        :param count:   读取数量
        :return:        布尔值列表，失败返回空列表
        """
        if not self.client:                                   # 未连接则返回空
            return []
        try:
            result = self.client.read_coils(                  # 发送读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.bits[:count])                  # 返回布尔值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def read_discrete_inputs(self, address: int, count: int) -> list:
        """
        FC 0x02 读取离散输入（只读，用于 BOOL 传感器信号）

        :param address: 起始地址
        :param count:   读取数量
        :return:        布尔值列表，失败返回空列表
        """
        if not self.client:                                   # 未连接则返回空
            return []
        try:
            result = self.client.read_discrete_inputs(        # 发送读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.bits[:count])                  # 返回布尔值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def read_input_registers(self, address: int, count: int) -> list:
        """
        FC 0x04 读取输入寄存器（只读，用于 WORD/FLOAT 模拟量采集）

        :param address: 起始地址
        :param count:   读取数量
        :return:        寄存器值列表，失败返回空列表
        """
        if not self.client:                                   # 未连接则返回空
            return []
        try:
            result = self.client.read_input_registers(        # 发送读取请求
                address=address,                              # 起始地址
                count=count,                                  # 读取数量
                device_id=self.unit_id                        # 从站 ID
            )
            if result.isError():                              # 检查响应是否出错
                return []                                     # 出错返回空列表
            return list(result.registers)                     # 返回寄存器值列表
        except ModbusException:                               # 捕获 Modbus 协议异常
            return []                                         # 异常返回空列表

    def write_register(self, address: int, value: int) -> bool:
        """
        FC 0x06 写入单个保持寄存器

        :param address: 寄存器地址
        :param value:   写入值（0~65535）
        :return:        True 写入成功，False 写入失败
        """
        if not self.client:                                   # 未连接则返回失败
            return False
        try:
            result = self.client.write_register(              # 发送写入请求
                address=address,                              # 目标地址
                value=value,                                  # 写入值
                device_id=self.unit_id                        # 从站 ID
            )
            return not result.isError()                       # 无错误返回 True
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败

    def write_registers(self, address: int, values: list) -> bool:
        """
        FC 0x10 写入多个保持寄存器

        :param address: 起始地址
        :param values:  写入值列表
        :return:        True 写入成功，False 写入失败
        """
        if not self.client:                                   # 未连接则返回失败
            return False
        try:
            result = self.client.write_registers(             # 发送批量写入请求
                address=address,                              # 起始地址
                values=values,                                # 值列表
                device_id=self.unit_id                        # 从站 ID
            )
            return not result.isError()                       # 无错误返回 True
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败

    def write_coil(self, address: int, value: bool) -> bool:
        """
        FC 0x05 写入单个线圈

        :param address: 线圈地址
        :param value:   True/False
        :return:        True 写入成功，False 写入失败
        """
        if not self.client:                                   # 未连接则返回失败
            return False
        try:
            result = self.client.write_coil(                  # 发送写入请求
                address=address,                              # 目标地址
                value=value,                                  # 写入值
                device_id=self.unit_id                        # 从站 ID
            )
            return not result.isError()                       # 无错误返回 True
        except ModbusException:                               # 捕获 Modbus 协议异常
            return False                                      # 异常返回失败
