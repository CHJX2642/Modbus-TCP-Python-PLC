"""
共享状态模块
用于数据采集线程和 Flask Web 服务之间的数据共享
使用线程安全的方式存储最新状态
"""

import threading                                              # 线程模块，用于线程锁
from datetime import datetime                                  # 时间模块，用于更新时间戳


class SharedState:
    """
    线程安全的共享状态存储类
    所有写操作通过锁保护，确保多线程环境下的数据一致性
    """

    def __init__(self):
        """初始化共享状态，创建线程锁和数据结构"""
        self._lock = threading.Lock()                          # 创建线程锁，保护共享数据

        # 采集值字典（变量键 -> 值）
        self.values = {}                                       # 存储最新的采集数据

        # 系统状态字典
        self.system = {
            "plc_connected": False,                            # PLC 连接状态
            "uptime_seconds": 0,                               # 系统运行时长（秒）
            "last_update": "",                                 # 最后更新时间
        }

    def update_values(self, values: dict):
        """
        线程安全地更新采集值

        :param values: 新的采集值字典
        """
        with self._lock:                                       # 获取线程锁
            self.values = dict(values)                         # 替换采集值字典（深拷贝）
            self.system["last_update"] = f"{datetime.now():%H:%M:%S}"  # 更新时间戳

    def update_system(self, **kwargs):
        """
        线程安全地更新系统状态字段

        :param kwargs: 要更新的字段名和值
        """
        with self._lock:                                       # 获取线程锁
            self.system.update(kwargs)                         # 更新指定字段

    def get_all(self) -> dict:
        """
        线程安全地获取所有状态数据的快照

        :return: 包含所有状态的字典副本
        """
        with self._lock:                                       # 获取线程锁
            return {                                           # 返回深拷贝的快照
                "values": dict(self.values),                   # 采集值副本
                "system": dict(self.system),                   # 系统状态副本
            }


state = SharedState()                                          # 创建全局单例实例
